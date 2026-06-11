import telebot
import smtplib
import time
import random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from threading import Thread, Lock
import threading
from telebot import types
from telebot.apihelper import ApiTelegramException
from ratelimit import limits, sleep_and_retry
import math # لإدارة المستلمين

bot_token = '7970050784:AAHss6d-FDah1DVdfTisXahcND5zCvwcTq4' # تم الإبقاء على التوكن لأنه ضروري لعمل البوت
bot = telebot.TeleBot(bot_token)
user_data = {}

# --- قفل لتحديث الحالة المتزامن ---
sending_status_lock = Lock()

# --- لوحة المفاتيح الرئيسية (تمت المراجعة لتطابق الصورة 1 بدقة) --- 
main_keyboard = types.InlineKeyboardMarkup(row_width=2)
btn_start_sending = types.InlineKeyboardButton('بدء الارسال', callback_data='start_sending')
btn_add_recipient = types.InlineKeyboardButton('إيميل الدعم', callback_data='add_recipient')
btn_add_sender = types.InlineKeyboardButton('اضف ايميل شد', callback_data='add_sender')
btn_set_seconds = types.InlineKeyboardButton('الثواني', callback_data='set_seconds')
btn_set_msg_count = types.InlineKeyboardButton('عدد الرسائل', callback_data='set_msg_count')
btn_set_subject = types.InlineKeyboardButton('الموضوع', callback_data='set_subject')
btn_set_template = types.InlineKeyboardButton('الكليشة', callback_data='set_template')
btn_show_accounts = types.InlineKeyboardButton('ايميلاتك', callback_data='show_accounts')
btn_show_all_info = types.InlineKeyboardButton('عرض المعلومات', callback_data='show_all_info')
btn_clear_all_info = types.InlineKeyboardButton('مسح الكل', callback_data='clear_all_info')
btn_updates = types.InlineKeyboardButton('للتواصل', url='https://t.me/FM_4_4MBOT')

main_keyboard.add(btn_start_sending)
main_keyboard.add(btn_add_recipient, btn_add_sender)
main_keyboard.add(btn_set_seconds, btn_set_msg_count)
main_keyboard.add(btn_set_subject, btn_set_template)
main_keyboard.add(btn_show_accounts, btn_show_all_info)
main_keyboard.add(btn_clear_all_info, btn_updates)

# --- الدوال الأساسية --- 

@bot.message_handler(commands=['start'])
def start(message):
    user_id = str(message.from_user.id)
    print(f"[DEBUG] User {user_id} started bot in chat {message.chat.id}")
    add_user_to_data(user_id)
    bot.reply_to(message, 'اهلا بك في بوت الرفع الخارجي', reply_markup=main_keyboard)

@bot.message_handler(commands=['stop'])
def stop(message):
    user_id = str(message.from_user.id)
    print(f"[DEBUG] User {user_id} requested stop in chat {message.chat.id}")
    user_info = user_data.get(user_id)
    if user_info and user_info.get('is_sending'):
        with sending_status_lock:
            user_info['stop_sending'] = True
            print(f"[DEBUG] Stop flag set for user {user_id}")
        bot.reply_to(message, 'تم طلب إيقاف الإرسال، قد يستغرق الأمر بضع لحظات...')
    else:
        bot.reply_to(message, 'لم تقم ببدء عملية الإرسال بعد أو أنها انتهت بالفعل.')

# --- معالج الأزرار (Callback Handler) --- 
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = str(call.from_user.id)
    add_user_to_data(user_id)
    user_info = user_data[user_id]

    try:
        msg_id = call.message.message_id
        chat_id = call.message.chat.id
        print(f"[DEBUG] Callback received: {call.data} from user {user_id} in chat {chat_id}, message {msg_id}")

        if call.data == 'add_recipient':
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text="""
            ادخل ايميل الدعم | مثال
اذا تبي ايميل واحد:
stopCA@telegram.org

عدة ايميلات:
abuse@telegram.org
abuse@telegram.org""", reply_markup=create_back_button('main_menu'))
            bot.register_next_step_handler(call.message, add_recipient, user_id)
        elif call.data == 'add_sender':
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text="""
            ادخل ايميل الشد مع كلمة مرور التطبيقات:
مثال:
hgehewheh8@gmail.com:ohsj knma bwnw lqmk
""", reply_markup=create_back_button('main_menu'))
            bot.register_next_step_handler(call.message, add_sender, user_id)
        elif call.data == 'set_seconds':
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text='ادخل عدد الثواني بين كل رسالة واخرى:', reply_markup=create_back_button('main_menu'))
            bot.register_next_step_handler(call.message, set_seconds, user_id)
        elif call.data == 'set_msg_count':
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text='ادخل عدد الرسائل التي تريد ارسالها (لكل ايميل شد):', reply_markup=create_back_button('main_menu')) # توضيح العدد لكل ايميل
            bot.register_next_step_handler(call.message, set_message_count, user_id)
        elif call.data == 'set_subject':
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text='ادخل موضوع الرسالة:', reply_markup=create_back_button('main_menu'))
            bot.register_next_step_handler(call.message, set_subject, user_id)
        elif call.data == 'set_template':
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text='ادخل الكليشة او محتوى الرسالة التي تريد ان تصل الى الدعم الفني:', reply_markup=create_back_button('main_menu'))
            bot.register_next_step_handler(call.message, set_template, user_id)
        elif call.data == 'start_sending':
            errors = []
            if not user_info['email_senders']: errors.append("لم تقم بإضافة ايميلات شد.")
            if not user_info['recipients']: errors.append("لم تقم بإضافة ايميل الدعم.")
            if not user_info['email_subject']: errors.append("لم تقم بإضافة الموضوع.")
            if not user_info['email_template']: errors.append("لم تقم بإضافة الكليشة.")
            if user_info['interval_seconds'] <= 0: errors.append("لم تقم بتحديد الثواني.")
            if user_info['message_count'] <= 0: errors.append("لم تقم بتحديد عدد الرسائل.")

            if errors:
                error_msg = "خطأ: \n" + "\n".join(errors)
                print(f"[DEBUG] Start sending validation failed for user {user_id}: {error_msg}")
                bot.answer_callback_query(call.id, error_msg, show_alert=True)
                return
            
            if user_info.get('is_sending'):
                 print(f"[DEBUG] User {user_id} tried to start sending while already sending.")
                 bot.answer_callback_query(call.id, "عملية الإرسال جارية بالفعل.", show_alert=True)
                 return

            print(f"[DEBUG] Starting send process for user {user_id} in chat {chat_id}, message {msg_id}")
            # لا نعدل الرسالة هنا، start_sending ستفعل ذلك
            # bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text='جارٍ بدء إرسال الرسائل...')
            start_sending(user_id, call.message) # تمرير الرسالة الأصلية مهم
        elif call.data == 'show_accounts':
            show_accounts(call.message, user_id)
        elif call.data == 'show_all_info':
            show_all_info(call.message, user_id)
        elif call.data == 'clear_all_info':
            confirm_keyboard = types.InlineKeyboardMarkup()
            yes_btn = types.InlineKeyboardButton('نعم', callback_data='confirm_clear')
            no_btn = types.InlineKeyboardButton('لا', callback_data='cancel_clear')
            confirm_keyboard.add(yes_btn, no_btn)
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text='هل أنت متأكد من حذف جميع المعلومات؟', reply_markup=confirm_keyboard)
        elif call.data == 'confirm_clear':
            print(f"[DEBUG] Clearing all info for user {user_id}")
            clear_all_info(user_id)
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text='تم مسح جميع المعلومات بنجاح!', reply_markup=create_back_button('main_menu'))
        elif call.data == 'cancel_clear':
             bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text='تم إلغاء عملية المسح.', reply_markup=main_keyboard)
        elif call.data == 'stop_sending':
            with sending_status_lock:
                 user_info['stop_sending'] = True
                 print(f"[DEBUG] Stop flag set via button for user {user_id}")
            bot.answer_callback_query(call.id, "سيتم إيقاف الإرسال قريباً...")
        elif call.data == 'main_menu':
             bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text='القائمة الرئيسية', reply_markup=main_keyboard)

    except ApiTelegramException as e:
        if "message is not modified" in str(e):
            # print(f"[DEBUG] Message not modified for user {user_id}, chat {chat_id}, message {msg_id}")
            bot.answer_callback_query(call.id, "لا يوجد تغيير.")
        else:
            print(f"[ERROR] Telegram API Exception in callback handler: {e}")
            bot.answer_callback_query(call.id, "حدث خطأ في التليجرام، يرجى المحاولة مرة أخرى.")
    except Exception as e:
        print(f"[ERROR] Unexpected Exception in callback handler: {e}")
        import traceback
        traceback.print_exc() # طباعة تفاصيل الخطأ الكاملة
        bot.answer_callback_query(call.id, "حدث خطأ غير متوقع.")

# --- دوال الإضافة والتعديل --- 

def add_user_to_data(user_id):
    if user_id not in user_data:
        print(f"[DEBUG] Initializing data for new user {user_id}")
        user_data[user_id] = {
            'email_senders': [],
            'email_passwords': [],
            'recipients': [],
            'email_subject': '',
            'email_template': '',
            'interval_seconds': 0,
            'message_count': 0, # عدد الرسائل لكل ايميل شد
            'is_sending': False,
            'stop_sending': False,
            'status_message_id': None,
            'sending_threads': [], # لتخزين الثريدات العاملة
            'sending_status': {} # لتخزين حالة كل ثريد (مرسل)
        }

def delete_previous_messages(message):
    try:
        # لا نحذف الرسالة الأصلية التي تحتوي على الأزرار
        # bot.delete_message(chat_id=message.chat.id, message_id=message.reply_to_message.message_id)
        bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        print(f"[DEBUG] Deleted user input message {message.message_id} in chat {message.chat.id}")
    except Exception as e:
        # print(f"[DEBUG] Failed to delete message {message.message_id} or reply_to message: {e}")
        pass

def add_recipient(message, user_id):
    delete_previous_messages(message)
    recipients = message.text.split()
    if recipients:
        user_data[user_id]['recipients'] = recipients
        print(f"[DEBUG] User {user_id} added {len(recipients)} recipients.")
        bot.send_message(message.chat.id, f'تمت إضافة {len(recipients)} ايميل دعم بنجاح!', reply_markup=main_keyboard)
    else:
        bot.send_message(message.chat.id, 'خطأ: لم يتم إدخال ايميلات. الرجاء المحاولة مرة أخرى.', reply_markup=create_back_button('add_recipient'))

def add_sender(message, user_id):
    delete_previous_messages(message)
    email_password_pairs = message.text.split('\n')
    added_count = 0
    failed_count = 0
    current_senders = user_data[user_id]['email_senders']
    current_passwords = user_data[user_id]['email_passwords']

    for pair in email_password_pairs:
        sender_email_password = pair.split(':')
        if len(sender_email_password) == 2:
            sender_email = sender_email_password[0].strip()
            sender_password = sender_email_password[1].strip()
            if sender_email and sender_password:
                if sender_email not in current_senders:
                    current_senders.append(sender_email)
                    current_passwords.append(sender_password)
                    added_count += 1
                else:
                    failed_count += 1
            else:
                failed_count += 1
        else:
            failed_count += 1

    reply_text = ""
    if added_count > 0:
        reply_text += f"تمت إضافة {added_count} ايميل شد بنجاح!\n"
    if failed_count > 0:
        reply_text += f'فشل إضافة {failed_count} ايميل (قد يكون مكررًا أو بصيغة خاطئة).'

    if not reply_text:
         reply_text = 'لم يتم إدخال ايميلات أو كانت الصيغة خاطئة.'

    print(f"[DEBUG] User {user_id} added {added_count} senders, failed {failed_count}.")
    bot.send_message(message.chat.id, reply_text, reply_markup=main_keyboard)

def set_seconds(message, user_id):
    delete_previous_messages(message)
    try:
        interval_seconds = int(message.text.strip())
        if interval_seconds > 0:
            user_data[user_id]['interval_seconds'] = interval_seconds
            print(f"[DEBUG] User {user_id} set interval to {interval_seconds} seconds.")
            bot.send_message(message.chat.id, f'تم تعيين الثواني إلى {interval_seconds}.', reply_markup=main_keyboard)
        else:
            bot.send_message(message.chat.id, 'خطأ: يجب أن يكون عدد الثواني أكبر من صفر.', reply_markup=create_back_button('set_seconds'))
    except ValueError:
        bot.send_message(message.chat.id, 'خطأ: الرجاء إدخال رقم صحيح للثواني.', reply_markup=create_back_button('set_seconds'))

def set_message_count(message, user_id):
    delete_previous_messages(message)
    try:
        message_count = int(message.text.strip())
        if message_count > 0:
            user_data[user_id]['message_count'] = message_count
            print(f"[DEBUG] User {user_id} set message count per sender to {message_count}.")
            bot.send_message(message.chat.id, f'تم تعيين عدد الرسائل لكل ايميل شد إلى {message_count}.', reply_markup=main_keyboard)
        else:
            bot.send_message(message.chat.id, 'خطأ: يجب أن يكون عدد الرسائل أكبر من صفر.', reply_markup=create_back_button('set_msg_count'))
    except ValueError:
        bot.send_message(message.chat.id, 'خطأ: الرجاء إدخال رقم صحيح لعدد الرسائل.', reply_markup=create_back_button('set_msg_count'))

def set_subject(message, user_id):
    delete_previous_messages(message)
    subject = message.text.strip()
    if subject:
        user_data[user_id]['email_subject'] = subject
        print(f"[DEBUG] User {user_id} set subject.")
        bot.send_message(message.chat.id, 'تم تعيين الموضوع بنجاح!', reply_markup=main_keyboard)
    else:
        bot.send_message(message.chat.id, 'خطأ: لم يتم إدخال الموضوع. الرجاء المحاولة مرة أخرى.', reply_markup=create_back_button('set_subject'))

def set_template(message, user_id):
    delete_previous_messages(message)
    template = message.text.strip()
    if template:
        user_data[user_id]['email_template'] = template
        print(f"[DEBUG] User {user_id} set template.")
        bot.send_message(message.chat.id, 'تم تعيين الكليشة بنجاح!', reply_markup=main_keyboard)
    else:
        bot.send_message(message.chat.id, 'خطأ: لم يتم إدخال الكليشة. الرجاء المحاولة مرة أخرى.', reply_markup=create_back_button('set_template'))

def show_accounts(message, user_id):
    user_info = user_data[user_id]
    senders_count = len(user_info['email_senders'])
    bot.edit_message_text(chat_id=message.chat.id, message_id=message.message_id, text=f'عدد ايميلاتك < {senders_count} >', reply_markup=create_back_button('main_menu'))

def show_all_info(message, user_id):
    user_info = user_data[user_id]
    info_text = "-- عرض المعلومات الحالية --\n"
    info_text += f"ايميلات الدعم: {', '.join(user_info['recipients']) if user_info['recipients'] else 'لم يتم التعيين'}\n"
    info_text += f"ايميلات الشد: {len(user_info['email_senders'])} ايميل\n"
    info_text += f"الموضوع: {user_info['email_subject'] if user_info['email_subject'] else 'لم يتم التعيين'}\n"
    info_text += f"الكليشة: {user_info['email_template'] if user_info['email_template'] else 'لم يتم التعيين'}\n"
    info_text += f"الثواني: {user_info['interval_seconds'] if user_info['interval_seconds'] > 0 else 'لم يتم التعيين'} ثانية\n"
    info_text += f"عدد الرسائل (لكل ايميل شد): {user_info['message_count'] if user_info['message_count'] > 0 else 'لم يتم التعيين'} رسالة\n" # توضيح العدد لكل ايميل
    info_text += "---------------------"
    bot.edit_message_text(chat_id=message.chat.id, message_id=message.message_id, text=info_text, reply_markup=create_back_button('main_menu'))

def clear_all_info(user_id):
    if user_id in user_data:
        # إيقاف أي عمليات إرسال جارية قبل المسح
        if user_data[user_id].get('is_sending'):
            print(f"[DEBUG] Stopping sending for user {user_id} before clearing info.")
            with sending_status_lock:
                user_data[user_id]['stop_sending'] = True
            # إعطاء فرصة للثريدات للتوقف
            time.sleep(2)
        
        # إعادة تعيين البيانات
        print(f"[DEBUG] Resetting data for user {user_id}.")
        user_data[user_id] = {
            'email_senders': [],
            'email_passwords': [],
            'recipients': [],
            'email_subject': '',
            'email_template': '',
            'interval_seconds': 0,
            'message_count': 0,
            'is_sending': False,
            'stop_sending': False,
            'status_message_id': None,
            'sending_threads': [],
            'sending_status': {}
        }

# --- دوال إرسال البريد الإلكتروني (معدلة للإرسال المتزامن) --- 

ONE_MINUTE = 60

@sleep_and_retry
@limits(calls=20, period=ONE_MINUTE)
def send_limited_message(*args, **kwargs):
    chat_id = args[0] if args else kwargs.get('chat_id')
    print(f"[DEBUG] Attempting send_message to chat {chat_id}")
    try:
        result = bot.send_message(*args, **kwargs)
        print(f"[DEBUG] send_message to chat {chat_id} successful.")
        return result
    except ApiTelegramException as e:
        print(f"[ERROR] Telegram API error sending message to chat {chat_id}: {e}")
        time.sleep(5)
        return None
    except Exception as e:
        print(f"[ERROR] Unexpected error sending message to chat {chat_id}: {e}")
        return None

@sleep_and_retry
@limits(calls=20, period=ONE_MINUTE)
def edit_limited_message_text(*args, **kwargs):
    chat_id = kwargs.get('chat_id')
    message_id = kwargs.get('message_id')
    text = kwargs.get('text', '')[:100] # Log first 100 chars
    print(f"[DEBUG] Attempting edit_message_text for chat {chat_id}, message {message_id}, text starts with: '{text}...'")
    try:
        result = bot.edit_message_text(*args, **kwargs)
        print(f"[DEBUG] edit_message_text for chat {chat_id}, message {message_id} successful.")
        return result
    except ApiTelegramException as e:
        if "message is not modified" not in str(e):
             print(f"[ERROR] Telegram API error editing message {message_id} in chat {chat_id}: {e}")
             time.sleep(5)
        else:
             # print(f"[DEBUG] Message {message_id} in chat {chat_id} not modified.")
             pass # لا يعتبر خطأ فادح
        return None # فشل التعديل أو لم يتغير
    except Exception as e:
        print(f"[ERROR] Unexpected error editing message {message_id} in chat {chat_id}: {e}")
        return None

def send_email(sender_email, sender_password, recipient, subject, message):
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient
    msg['Subject'] = subject
    msg.attach(MIMEText(message, 'plain', 'utf-8'))
    msg.add_header('User-Agent', 'iPhone Mail (14F5089a)')

    try:
        # print(f"[DEBUG] Attempting to send email from {sender_email} to {recipient}")
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        # print(f"[DEBUG] Email sent successfully from {sender_email} to {recipient}")
        return True, None
    except smtplib.SMTPAuthenticationError:
        print(f"[ERROR] SMTP Authentication failed for {sender_email}")
        return False, "auth_failed"
    except smtplib.SMTPServerDisconnected:
        print(f"[WARN] SMTP Server disconnected for {sender_email}. Retrying might be needed.")
        time.sleep(5)
        return False, "server_disconnected"
    except Exception as e:
        print(f"[ERROR] Error sending email from {sender_email} to {recipient}: {str(e)}")
        return False, str(e)

def send_single_sender_task(user_id, sender_email, sender_password, recipients, subject, message_body, interval, message_count):
    """مهمة إرسال الرسائل لمرسل واحد."""
    print(f"[DEBUG] Starting sender task for {sender_email} (User: {user_id})")
    user_info = user_data[user_id]
    sender_status = user_info['sending_status'][sender_email]
    recipient_index = 0
    local_success = 0
    local_failed = 0
    local_auth_failed = 0
    is_blocked = False

    for i in range(message_count):
        # التحقق من إشارة الإيقاف
        with sending_status_lock:
            if user_info['stop_sending']:
                sender_status['status'] = 'stopped'
                print(f"[DEBUG] Sender task for {sender_email} stopped by flag.")
                break
        
        # إذا تم حظر المرسل بسبب فشل المصادقة، توقف عن المحاولة
        if is_blocked:
            print(f"[DEBUG] Sender task for {sender_email} stopping due to previous auth failure.")
            break

        current_recipient = recipients[recipient_index]
        
        sent, error_type = send_email(sender_email, sender_password, current_recipient, subject, message_body)

        with sending_status_lock:
            if sent:
                sender_status['sent'] += 1
                local_success += 1
            else:
                sender_status['failed'] += 1
                local_failed += 1
                if error_type == "auth_failed":
                    sender_status['auth_failed'] = True
                    local_auth_failed += 1
                    is_blocked = True # توقف عن استخدام هذا المرسل
                    sender_status['status'] = 'auth_failed'
                    print(f"[WARN] Sender {sender_email} marked as blocked due to auth failure.")
            
            # تحديث الحالة العامة للمرسل
            if not is_blocked and sender_status['status'] != 'stopped':
                 sender_status['status'] = 'sending' # لا يزال يرسل أو يحاول

        # الانتقال للمستلم التالي
        recipient_index = (recipient_index + 1) % len(recipients)

        # الانتظار قبل إرسال الرسالة التالية (إذا لم تكن الأخيرة ولم يتم الإيقاف)
        if i < message_count - 1 and not user_info['stop_sending'] and not is_blocked:
            # print(f"[DEBUG] Sender {sender_email} sleeping for {interval} seconds.")
            time.sleep(interval)

    # تحديث الحالة النهائية للمرسل إذا لم يتم حظره أو إيقافه
    with sending_status_lock:
        if sender_status['status'] == 'sending': # إذا كان لا يزال يرسل ولم يتوقف أو يحظر
             sender_status['status'] = 'completed'
        elif not is_blocked and not user_info['stop_sending']: # إذا لم يكتمل لكن لم يحظر أو يوقف
             sender_status['status'] = 'error' # ربما انتهى بسبب خطأ آخر غير المصادقة

    print(f"[DEBUG] Sender task for {sender_email} finished. Sent: {local_success}, Failed: {local_failed}, Auth Failed: {local_auth_failed}, Final Status: {sender_status['status']}")

def update_status_message(user_id, chat_id, start_time):
    """تحديث رسالة الحالة بشكل دوري."""
    print(f"[DEBUG] Starting status update thread for user {user_id}, chat {chat_id}")
    user_info = user_data[user_id]
    status_msg_id = user_info.get('status_message_id')
    if not status_msg_id:
        print(f"[ERROR] Cannot update status for user {user_id}, chat {chat_id}: status_message_id is missing!")
        return # لا يمكن التحديث بدون معرف الرسالة
    print(f"[DEBUG] Status update thread will target message {status_msg_id} in chat {chat_id}")

    status_keyboard = types.InlineKeyboardMarkup()
    stop_btn = types.InlineKeyboardButton('إيقاف الإرسال', callback_data='stop_sending')
    status_keyboard.add(stop_btn)

    last_status_text = "" # لتجنب التعديل بنفس النص

    while True:
        print(f"[DEBUG] Status update loop running for chat {chat_id}, message {status_msg_id}")
        current_status_text = ""
        all_threads_done = False
        active_threads = 0 # إعادة حسابها في كل دورة

        with sending_status_lock:
            if not user_info.get('is_sending'): # التحقق إذا انتهت العملية الرئيسية
                print(f"[DEBUG] Status update loop for chat {chat_id}: 'is_sending' is False, breaking loop.")
                break
            
            total_sent = 0
            total_failed = 0
            total_auth_failed = 0
            # active_threads = 0 # تم نقلها للخارج
            blocked_senders_count = 0
            completed_threads = 0
            stopped_threads = 0
            error_threads = 0

            # التحقق من حالة الثريدات الحقيقية بدلاً من الاعتماد فقط على sending_status
            live_sender_threads = [t for t in user_info.get('sending_threads', []) if t.is_alive()]
            active_threads = len(live_sender_threads)
            print(f"[DEBUG] Status update for chat {chat_id}: Found {active_threads} live sender threads.")

            # حساب الإحصائيات من sending_status
            for email, status in user_info['sending_status'].items():
                total_sent += status['sent']
                total_failed += status['failed']
                if status['auth_failed']: total_auth_failed += 1
                # if status['status'] == 'sending': active_threads += 1 # الاعتماد على is_alive أدق
                if status['status'] == 'auth_failed': blocked_senders_count += 1
                if status['status'] == 'completed': completed_threads += 1
                if status['status'] == 'stopped': stopped_threads += 1
                if status['status'] == 'error': error_threads += 1
            
            total_target = len(user_info['email_senders']) * user_info['message_count']
            elapsed_time = time.time() - start_time
            time_str = time.strftime("%H:%M:%S", time.gmtime(elapsed_time))

            current_status_text = (
                "عملية الإرسال جارية...\n"
                f"الوقت المنقضي: {time_str}\n"
                f"الهدف الإجمالي: {total_target} رسالة\n"
                f"ايميلات شد نشطة: {active_threads}/{len(user_info['email_senders'])}\n" # استخدام عدد الثريدات الحية
                f"ايميلات محظورة: {blocked_senders_count}\n"
                "--------------------\n"
                f"إجمالي المرسل: {total_sent}"
                f"\nإجمالي الفشل: {total_failed} (منها فشل مصادقة: {total_auth_failed})"
                f"\nالتقدم التقريبي: {((total_sent + total_failed) / total_target * 100) if total_target > 0 else 0:.1f}%"
            )
            
            # التحقق إذا كان يجب إيقاف التحديث (جميع الثريدات انتهت)
            # all_threads_done = (active_threads == 0)
            # تعديل: نوقف التحديث فقط إذا كانت is_sending أصبحت False (يتم تعيينها في manage_sending_threads بعد join)
            all_threads_done = not user_info.get('is_sending')
            if all_threads_done:
                 print(f"[DEBUG] Status update loop for chat {chat_id}: All threads seem done (is_sending is False), preparing to break.")

        # --- تحديث الرسالة خارج القفل --- 
        if current_status_text != last_status_text:
            print(f"[DEBUG] Status update for chat {chat_id}: Text changed, attempting edit.")
            edit_result = edit_limited_message_text(chat_id=chat_id, message_id=status_msg_id, text=current_status_text, reply_markup=status_keyboard)
            if edit_result:
                last_status_text = current_status_text # تحديث النص الأخير فقط عند النجاح
                print(f"[DEBUG] Status update for chat {chat_id}, message {status_msg_id} successful.")
            else:
                print(f"[WARN] Status update for chat {chat_id}, message {status_msg_id} failed or message not modified.")
                # هل يجب أن نتوقف هنا؟ ربما تم حذف الرسالة؟
                # يمكن إضافة منطق لإعادة محاولة إرسال رسالة جديدة إذا فشل التعديل عدة مرات
                pass
        else:
            print(f"[DEBUG] Status update for chat {chat_id}: Text not changed, skipping edit.")

        if all_threads_done:
            break # الخروج من حلقة التحديث
            
        # الانتظار قبل التحديث التالي
        print(f"[DEBUG] Status update thread for chat {chat_id} sleeping for 5 seconds.")
        time.sleep(5) # تحديث كل 5 ثواني
    
    print(f"[DEBUG] Status update thread for user {user_id}, chat {chat_id} finished.")

def manage_sending_threads(user_id, chat_id, initial_message_id):
    """إدارة عملية الإرسال المتزامن."""
    print(f"[DEBUG] Entered manage_sending_threads for user {user_id}, chat {chat_id}, initial message {initial_message_id}")
    user_info = user_data[user_id]
    
    with sending_status_lock:
        user_info['is_sending'] = True
        user_info['stop_sending'] = False
        user_info['sending_threads'] = []
        user_info['sending_status'] = {}
        user_info['status_message_id'] = None # إعادة تعيينه قبل محاولة التعديل/الإرسال
        start_time = time.time()
        print(f"[DEBUG] Initialized sending state for user {user_id}, chat {chat_id}")

    senders = user_info['email_senders']
    passwords = user_info['email_passwords']
    recipients = user_info['recipients']
    subject = user_info['email_subject']
    message_body = user_info['email_template']
    interval = user_info['interval_seconds']
    message_count_per_sender = user_info['message_count']

    # --- إرسال أو تعديل رسالة الحالة الأولية --- 
    initial_status_text = (
        "بدء عملية الارسال المتزامن...\n"
        f"عدد ايميلات الشد: {len(senders)}\n"
        f"عدد الرسائل لكل ايميل: {message_count_per_sender}\n"
        f"الهدف الإجمالي: {len(senders) * message_count_per_sender} رسالة\n"
        f"الفاصل الزمني لكل ايميل: {interval} ثانية\n"
        "--------------------\n"
        "جارٍ تهيئة المهام..."
    )
    status_keyboard = types.InlineKeyboardMarkup()
    stop_btn = types.InlineKeyboardButton('إيقاف الإرسال', callback_data='stop_sending')
    status_keyboard.add(stop_btn)

    print(f"[DEBUG] Attempting to edit initial message {initial_message_id} in chat {chat_id}")
    status_message = edit_limited_message_text(chat_id=chat_id, message_id=initial_message_id, text=initial_status_text, reply_markup=status_keyboard)
    if status_message:
        user_info['status_message_id'] = status_message.message_id
        print(f"[DEBUG] Successfully edited initial message. New status message ID: {status_message.message_id}")
    else:
        print(f"[WARN] Failed to edit initial message {initial_message_id}. Attempting to send a new one.")
        # محاولة تعديل الرسالة الأصلية فشلت، ربما تم حذفها أو حدث خطأ آخر
        # نحاول إرسال رسالة جديدة كبديل
        fallback_message = send_limited_message(chat_id, initial_status_text, reply_markup=status_keyboard)
        if fallback_message:
            user_info['status_message_id'] = fallback_message.message_id
            print(f"[DEBUG] Successfully sent fallback status message. New status message ID: {fallback_message.message_id}")
        else:
             print(f"[ERROR] User {user_id} (Chat {chat_id}): Failed to send/edit initial status message. Aborting send process.")
             with sending_status_lock:
                 user_info['is_sending'] = False # إيقاف العملية إذا لم نتمكن من إظهار الحالة
             return
    # --- نهاية إعداد رسالة الحالة --- 

    # --- بدء ثريدات الإرسال لكل مرسل --- 
    threads = []
    print(f"[DEBUG] Starting sender threads for chat {chat_id}...")
    for i, sender_email in enumerate(senders):
        sender_password = passwords[i]
        # تهيئة حالة هذا المرسل
        with sending_status_lock:
            user_info['sending_status'][sender_email] = {'sent': 0, 'failed': 0, 'auth_failed': False, 'status': 'starting'}
        
        thread = Thread(target=send_single_sender_task, args=(user_id, sender_email, sender_password, recipients, subject, message_body, interval, message_count_per_sender))
        threads.append(thread)
        thread.start()
        print(f"[DEBUG] Started thread for sender {sender_email}")
        time.sleep(0.1) # فاصل بسيط بين بدء الثريدات لتجنب الضغط اللحظي

    with sending_status_lock:
        user_info['sending_threads'] = threads
        print(f"[DEBUG] All {len(threads)} sender threads started for chat {chat_id}.")
    # --- نهاية بدء الثريدات --- 

    # --- بدء ثريد تحديث الحالة --- 
    print(f"[DEBUG] Starting status updater thread for chat {chat_id}, message {user_info['status_message_id']}")
    status_updater_thread = Thread(target=update_status_message, args=(user_id, chat_id, start_time))
    status_updater_thread.start()

    # --- انتظار انتهاء جميع ثريدات الإرسال --- 
    print(f"[DEBUG] Main thread for chat {chat_id} waiting for {len(threads)} sender threads to join...")
    for i, thread in enumerate(threads):
        thread.join()
        print(f"[DEBUG] Sender thread {i+1}/{len(threads)} joined for chat {chat_id}.")
    print(f"[DEBUG] All sender threads joined for chat {chat_id}.")

    # --- تعيين is_sending إلى False قبل انتظار ثريد التحديث --- 
    # هذا يسمح لثريد التحديث بالخروج من حلقته
    with sending_status_lock:
        print(f"[DEBUG] Setting is_sending=False for chat {chat_id} after sender threads joined.")
        user_info['is_sending'] = False

    # --- انتظار انتهاء ثريد تحديث الحالة --- 
    print(f"[DEBUG] Main thread for chat {chat_id} waiting for status updater thread to join...")
    status_updater_thread.join()
    print(f"[DEBUG] Status updater thread joined for chat {chat_id}.")

    # --- حساب النتائج النهائية وتحديث الرسالة --- 
    print(f"[DEBUG] Calculating final results for chat {chat_id}...")
    final_summary = ""
    final_status_message_id = user_info.get('status_message_id') # استخدام المعرف الأخير

    if not final_status_message_id:
        print(f"[ERROR] Cannot send final summary for chat {chat_id}: status_message_id is missing!")
        # تنظيف الحالة على أي حال
        with sending_status_lock:
            user_info['stop_sending'] = False
            user_info['status_message_id'] = None
            user_info['sending_threads'] = []
            user_info['sending_status'] = {}
        return

    with sending_status_lock:
        total_sent = 0
        total_failed = 0
        total_auth_failed = 0
        blocked_senders_count = 0
        completed_count = 0
        stopped_count = 0
        final_status_details = []

        for email, status in user_info['sending_status'].items():
            total_sent += status['sent']
            total_failed += status['failed']
            if status['auth_failed']: 
                total_auth_failed += 1
                blocked_senders_count += 1
                final_status_details.append(f"- {email}: فشل المصادقة")
            elif status['status'] == 'completed':
                completed_count += 1
                final_status_details.append(f"- {email}: اكتمل ({status['sent']}/{message_count_per_sender})")
            elif status['status'] == 'stopped':
                stopped_count += 1
                final_status_details.append(f"- {email}: توقف ({status['sent']}/{message_count_per_sender})")
            else: # error or other
                 final_status_details.append(f"- {email}: خطأ ({status['sent']}/{message_count_per_sender}, فشل: {status['failed']})")

        elapsed_time = time.time() - start_time
        time_str = time.strftime("%H:%M:%S", time.gmtime(elapsed_time))

        final_summary = "\n---"
        if user_info['stop_sending']: # التحقق من علامة الإيقاف
            final_summary += "\nتم إيقاف عملية الإرسال بناءً على طلبك."
        elif completed_count == len(senders):
            final_summary += "\nاكتملت عملية الإرسال لجميع الايميلات بنجاح."
        else:
            final_summary += "\nانتهت عملية الإرسال."
        
        final_summary += (
            f"\n\nالنتائج النهائية (الوقت: {time_str}):" 
            f"\nإجمالي المرسل: {total_sent}"
            f"\nإجمالي الفشل: {total_failed} (منها فشل مصادقة: {total_auth_failed})"
            f"\nايميلات مكتملة: {completed_count}/{len(senders)}"
            f"\nايميلات متوقفة: {stopped_count}/{len(senders)}"
            f"\nايميلات محظورة: {blocked_senders_count}/{len(senders)}"
        )
        
        # إضافة تفاصيل حالة كل ايميل إذا كان العدد قليلاً
        if len(final_status_details) <= 15:
             final_summary += "\n\nتفاصيل الحالة لكل ايميل:"
             final_summary += "\n" + "\n".join(final_status_details)

        # استخراج الجزء الأول من النص الأولي (قبل الخط الفاصل)
        # هذا يفترض أن النص الأولي لا يزال متاحاً، وهو ليس كذلك هنا.
        # سنستخدم نصاً ثابتاً بدلاً منه.
        final_text = "انتهت عملية الإرسال." + final_summary

        print(f"[DEBUG] Attempting to send final summary to chat {chat_id}, message {final_status_message_id}")
        # تحديث رسالة الحالة للمرة الأخيرة بلوحة المفاتيح الرئيسية
        edit_limited_message_text(chat_id=chat_id, message_id=final_status_message_id, text=final_text, reply_markup=create_back_button('main_menu'))
        print(f"[DEBUG] Final summary edit attempt finished for chat {chat_id}.")

        # تنظيف الحالة
        print(f"[DEBUG] Cleaning up final state for user {user_id}, chat {chat_id}")
        user_info['stop_sending'] = False # إعادة تعيين علامة الإيقاف
        user_info['status_message_id'] = None
        user_info['sending_threads'] = []
        user_info['sending_status'] = {}
        print(f"[DEBUG] Sending process fully completed for user {user_id}, chat {chat_id}.")

def start_sending(user_id, original_message):
    # استخدام ثريد رئيسي لإدارة العملية بأكملها
    chat_id = original_message.chat.id # <-- الحصول على chat_id
    message_id = original_message.message_id # <-- الحصول على message_id الأولي
    print(f"[DEBUG] start_sending called for user {user_id}, chat {chat_id}, message {message_id}")
    manager_thread = Thread(target=manage_sending_threads, args=(user_id, chat_id, message_id)) # <-- تمرير chat_id و message_id
    manager_thread.start()

# --- دوال مساعدة --- 
def create_back_button(callback_data):
    back_keyboard = types.InlineKeyboardMarkup()
    back_btn = types.InlineKeyboardButton("رجوع", callback_data=callback_data)
    back_keyboard.add(back_btn)
    return back_keyboard

# --- تشغيل البوت --- 
if __name__ == '__main__':
    print("Bot is running with concurrent sending logic and DEBUG prints...")
    while True:
        try:
            bot.polling(none_stop=True)
        except Exception as e:
            print(f"[ERROR] Bot polling crashed: {e}")
            import traceback
            traceback.print_exc()
            print("Restarting polling in 15 seconds...")
            time.sleep(15)

