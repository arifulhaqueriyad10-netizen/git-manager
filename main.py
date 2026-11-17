import logging
import uuid
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    ConversationHandler
)
from telegram.request import HTTPXRequest

# --- CONFIGURATION ---
BOT_TOKEN = "9034843504:AAHdSTHywvfhMt8IS_N59HiMO690D61RMKY"
OWNER_ID = 6417430059

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- IN-MEMORY DATABASE ---
admins = set([OWNER_ID])
global_channels = []  # Global channels added by Admins/Owner
user_channels = {}    # Personal channels added by users: {user_id: ["@channel1", "-100xxx"]}
files_db = {}         # {file_key: {"file_id": str, "type": str, "owner": int, "name": str}}
bot_users = set()

# --- STATES FOR CONVERSATIONS ---
WAITING_FILE = 1
WAITING_ADMIN_CHANNEL_ADD = 2
WAITING_USER_CHANNEL_ADD = 3
WAITING_ADMIN_ADD = 4
WAITING_BROADCAST = 5

# --- FONT & CUSTOM TELEGRAM EMOJIS ---
def sc(text: str) -> str:
    """Converts text to Small Caps font."""
    normal = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    small = "ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ0123456789"
    return text.translate(str.maketrans(normal, small))

def bold_sc(text: str) -> str:
    return f"<b>{sc(text)}</b>"

# Custom Premium Telegram Emojis for Message Responses
E_CROWN = '<tg-emoji emoji-id="6154611916678369390">👑</tg-emoji>'
E_STAR = '<tg-emoji emoji-id="5267394977540889773">🌟</tg-emoji>'
E_CLIP = '<tg-emoji emoji-id="6154729229415093721">📎</tg-emoji>'
E_MEGAPHONE = '<tg-emoji emoji-id="6154631793787015439">📣</tg-emoji>'
E_LOCK = '<tg-emoji emoji-id="6154565990593073474">🔒</tg-emoji>'
E_CHECK = '<tg-emoji emoji-id="6154718341672997377">✔</tg-emoji>'
E_GIFT = '<tg-emoji emoji-id="6154314868150243661">🎁</tg-emoji>'
E_MEMO = '<tg-emoji emoji-id="5337310516769467285">📝</tg-emoji>'
E_BACK = '<tg-emoji emoji-id="5429651785352501917">↗️</tg-emoji>'
E_GUN = '<tg-emoji emoji-id="5303040006347046717">🔫</tg-emoji>'
E_JUICE = '<tg-emoji emoji-id="5303548912726982102">🧃</tg-emoji>'
E_SMOKE = '<tg-emoji emoji-id="5870568528049868382">🚬</tg-emoji>'
E_WAIT = '<tg-emoji emoji-id="6154603635981423575">⏳</tg-emoji>'
E_ROBOT = '<tg-emoji emoji-id="5267102967009402987">👾</tg-emoji>'
E_PARTY = '<tg-emoji emoji-id="5303178192624823421">🎊</tg-emoji>'
E_PIN = '<tg-emoji emoji-id="6154635564768300782">📌</tg-emoji>'
E_HEART = '<tg-emoji emoji-id="5870681447035047985">❤️</tg-emoji>'
E_COMP = '<tg-emoji emoji-id="5193177581888755275">💻</tg-emoji>'

# --- HELPER FUNCTIONS ---
async def check_user_subscribed(bot, user_id: int, required_channels: list) -> bool:
    """Checks subscription status for a list of channels."""
    if user_id in admins:
        return True

    for ch in required_channels:
        try:
            member = await bot.get_chat_member(chat_id=ch, user_id=user_id)
            if member.status in ['left', 'kicked']:
                return False
        except Exception as e:
            logging.error(f"Error checking channel {ch}: {e}")
            return False
    return True

async def send_force_join_msg(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, required_channels: list, start_param: str = ""):
    """Sends Force Join message with inline buttons."""
    bot_info = await context.bot.get_me()
    join_buttons = []

    for idx, ch in enumerate(required_channels, 1):
        try:
            chat = await context.bot.get_chat(ch)
            invite_link = chat.invite_link or (f"https://t.me/{chat.username.lstrip('@')}" if chat.username else f"https://t.me/{bot_info.username}")
            join_buttons.append([InlineKeyboardButton(
                text=sc(f'Join Channel {idx}'), 
                url=invite_link, 
                style="primary", 
                icon_custom_emoji_id="6154635564768300782"
            )])
        except Exception:
            pass

    verify_url = f"https://t.me/{bot_info.username}?start={start_param}" if start_param else f"https://t.me/{bot_info.username}?start=verify"
    join_buttons.append([InlineKeyboardButton(
        text=sc('Verify Subscription'), 
        url=verify_url, 
        style="success", 
        icon_custom_emoji_id="6154718341672997377"
    )])

    msg = (
        f"{E_LOCK} {bold_sc('ACCESS DENIED!')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{E_WAIT} {bold_sc('Aapko is file / bot features ko access karne ke liye niche diye gaye channels join karne honge.')}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{E_PIN} {bold_sc('Channels join karne ke baad Verify button par click karein!')}"
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(msg, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(join_buttons))
    else:
        await update.message.reply_html(msg, reply_markup=InlineKeyboardMarkup(join_buttons))

def get_main_keyboard(user_id: int):
    """Generates clean & perfectly fitted main menu keyboard."""
    keyboard = [
        [
            InlineKeyboardButton(text=sc('Upload New File'), callback_data="btn_upload", style="primary", icon_custom_emoji_id="6154729229415093721"),
            InlineKeyboardButton(text=sc('Remove Saved File'), callback_data="btn_remove_file_menu", style="danger", icon_custom_emoji_id="5303040006347046717")
        ],
        [
            InlineKeyboardButton(text=sc('Share My Stored Files'), callback_data="btn_share_file", style="success", icon_custom_emoji_id="6154314868150243661")
        ],
        # User Personal Channel Controls
        [
            InlineKeyboardButton(text=sc('Add Channel Link'), callback_data="user_add_ch", style="primary", icon_custom_emoji_id="6154631793787015439"),
            InlineKeyboardButton(text=sc('View Channels List'), callback_data="user_list_ch", style="primary", icon_custom_emoji_id="5337310516769467285")
        ],
        [
            InlineKeyboardButton(text=sc('Remove Joined Channel'), callback_data="user_rem_ch_menu", style="danger", icon_custom_emoji_id="5870568528049868382")
        ]
    ]

    # Owner & Admin Extra Commands
    if user_id in admins:
        keyboard.append([
            InlineKeyboardButton(text=sc('Add Global Channel'), callback_data="admin_add_ch", style="primary", icon_custom_emoji_id="6154611916678369390"),
            InlineKeyboardButton(text=sc('Global Channel List'), callback_data="admin_list_ch", style="primary", icon_custom_emoji_id="5337310516769467285")
        ])
        keyboard.append([
            InlineKeyboardButton(text=sc('Remove Global Channel'), callback_data="admin_rem_ch_menu", style="danger", icon_custom_emoji_id="5870568528049868382"),
            InlineKeyboardButton(text=sc('Send Broadcast Msg'), callback_data="admin_broadcast", style="success", icon_custom_emoji_id="5267102967009402987")
        ])

    # Owner Only Commands
    if user_id == OWNER_ID:
        keyboard.append([
            InlineKeyboardButton(text=sc('Add Bot Admin'), callback_data="admin_add_admin", style="primary", icon_custom_emoji_id="6154611916678369390"),
            InlineKeyboardButton(text=sc('View Admins List'), callback_data="admin_list_admin", style="primary", icon_custom_emoji_id="5303548912726982102")
        ])
        keyboard.append([
            InlineKeyboardButton(text=sc('Remove Bot Admin'), callback_data="admin_rem_admin_menu", style="danger", icon_custom_emoji_id="6154565990593073474")
        ])

    return InlineKeyboardMarkup(keyboard)

def get_back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton(text=sc('Back to Menu'), callback_data="main_menu", style="danger", icon_custom_emoji_id="5429651785352501917")]])

# --- START COMMAND HANDLER ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Completely ignore updates from groups/channels
    if update.effective_chat and update.effective_chat.type != "private":
        return

    user = update.effective_user
    bot_users.add(user.id)
    bot_info = await context.bot.get_me()

    args = context.args
    # Deep linking check for shared files
    if args and args[0] != "verify":
        file_key = args[0]
        if file_key in files_db:
            f_data = files_db[file_key]
            file_owner = f_data["owner"]

            req_channels = list(set(global_channels + user_channels.get(file_owner, [])))

            if not await check_user_subscribed(context.bot, user.id, req_channels):
                await send_force_join_msg(update, context, user.id, req_channels, start_param=file_key)
                return

            await update.message.reply_html(f"{E_PARTY} {bold_sc('File Delivered Successfully!')}")
            if f_data["type"] == "document":
                await update.message.reply_document(document=f_data["file_id"])
            elif f_data["type"] == "photo":
                await update.message.reply_photo(photo=f_data["file_id"])
            elif f_data["type"] == "video":
                await update.message.reply_video(video=f_data["file_id"])
            elif f_data["type"] == "audio":
                await update.message.reply_audio(audio=f_data["file_id"])
            return
        else:
            await update.message.reply_html(f"{E_MEMO} {bold_sc('Invalid or Deleted File Link!')}")
            return

    # Check Global Force Join Channels for General Access
    if not await check_user_subscribed(context.bot, user.id, global_channels):
        await send_force_join_msg(update, context, user.id, global_channels)
        return

    # --- FULL DETAILED WELCOME MESSAGE ---
    welcome_msg = (
        f"{E_STAR} {bold_sc('WELCOME TO ADVANCED FILE STORAGE SYSTEM')} {E_STAR}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{E_ROBOT} <b>{sc('Bot Username')}</b> <b>:</b> @{bot_info.username}\n"
        f"{E_COMP} <b>{sc('Account Name')}</b> <b>:</b> <b>{user.full_name}</b>\n"
        f"{E_CLIP} <b>{sc('Telegram User ID')}</b> <b>:</b> <code>{user.id}</code>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{E_HEART} {bold_sc('SELECT AN OPTION FROM THE MENU BELOW TO PROCEED')}"
    )

    await update.message.reply_html(welcome_msg, reply_markup=get_main_keyboard(user.id))

# --- BUTTON HANDLER ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Completely ignore updates from groups/channels
    if update.effective_chat and update.effective_chat.type != "private":
        return

    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    # Main Menu Navigation
    if data == "main_menu":
        if not await check_user_subscribed(context.bot, user_id, global_channels):
            await send_force_join_msg(update, context, user_id, global_channels)
            return ConversationHandler.END

        bot_info = await context.bot.get_me()
        
        msg = (
            f"{E_STAR} {bold_sc('WELCOME TO ADVANCED FILE STORAGE SYSTEM')} {E_STAR}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{E_ROBOT} <b>{sc('Bot Username')}</b> <b>:</b> @{bot_info.username}\n"
            f"{E_COMP} <b>{sc('Account Name')}</b> <b>:</b> <b>{query.from_user.full_name}</b>\n"
            f"{E_CLIP} <b>{sc('Telegram User ID')}</b> <b>:</b> <code>{user_id}</code>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{E_HEART} {bold_sc('SELECT AN OPTION FROM THE MENU BELOW TO PROCEED')}"
        )
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=get_main_keyboard(user_id))
        return ConversationHandler.END

    # Global Gatekeeper check
    if not await check_user_subscribed(context.bot, user_id, global_channels):
        await send_force_join_msg(update, context, user_id, global_channels)
        return ConversationHandler.END

    # UPLOAD FILE TRIGGER
    if data == "btn_upload":
        await query.edit_message_text(
            f"{E_CLIP} {bold_sc('Please send/upload your file now (Document, Photo, Video, Audio):')}",
            parse_mode='HTML',
            reply_markup=get_back_keyboard()
        )
        return WAITING_FILE

    # REMOVE FILE MENU
    elif data == "btn_remove_file_menu":
        user_files = {k: v for k, v in files_db.items() if user_id == OWNER_ID or v["owner"] == user_id}
        if not user_files:
            await query.edit_message_text(
                f"{E_MEMO} {bold_sc('You have no uploaded files to remove!')}",
                parse_mode='HTML',
                reply_markup=get_back_keyboard()
            )
            return ConversationHandler.END

        file_list_txt = f"{E_CLIP} {bold_sc('Your Uploaded Files List:')}\n\n"
        buttons = []
        for idx, (fid, fval) in enumerate(user_files.items(), 1):
            file_list_txt += f"<b>{idx}.</b> {fval.get('name', 'File')} (Key: <code>{fid}</code>)\n"
            buttons.append([InlineKeyboardButton(
                text=sc(f"Delete: {fval.get('name', fid)[:15]}"), 
                callback_data=f"delfile_{fid}", 
                style="danger", 
                icon_custom_emoji_id="5303040006347046717"
            )])
        buttons.append([InlineKeyboardButton(text=sc('Back to Menu'), callback_data="main_menu", style="primary", icon_custom_emoji_id="5429651785352501917")])

        await query.edit_message_text(
            f"{file_list_txt}\n{E_SMOKE} {bold_sc('Select a file below to delete:')}",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return ConversationHandler.END

    # DELETE FILE ACTION
    elif data.startswith("delfile_"):
        fid = data.split("_")[1]
        if fid in files_db:
            if user_id == OWNER_ID or files_db[fid]["owner"] == user_id:
                del files_db[fid]
                await query.edit_message_text(f"{E_CHECK} {bold_sc('File Removed Successfully!')}", parse_mode='HTML', reply_markup=get_back_keyboard())
            else:
                await query.edit_message_text(f"{E_LOCK} {bold_sc('Unauthorized file access!')}", parse_mode='HTML', reply_markup=get_back_keyboard())
        else:
            await query.edit_message_text(f"{E_MEMO} {bold_sc('File not found or already deleted.')}", parse_mode='HTML', reply_markup=get_back_keyboard())
        return ConversationHandler.END

    # SHARE FILE MENU
    elif data == "btn_share_file":
        user_files = {k: v for k, v in files_db.items() if user_id == OWNER_ID or v["owner"] == user_id}
        if not user_files:
            await query.edit_message_text(f"{E_MEMO} {bold_sc('You have not uploaded any files yet!')}", parse_mode='HTML', reply_markup=get_back_keyboard())
            return ConversationHandler.END

        buttons = []
        for fid, fval in user_files.items():
            buttons.append([InlineKeyboardButton(
                text=sc(f"Get Link: {fval.get('name', fid)[:15]}"), 
                callback_data=f"getlink_{fid}", 
                style="success", 
                icon_custom_emoji_id="6154314868150243661"
            )])
        buttons.append([InlineKeyboardButton(text=sc('Back to Menu'), callback_data="main_menu", style="primary", icon_custom_emoji_id="5429651785352501917")])

        await query.edit_message_text(f"{E_PARTY} {bold_sc('Select a file to get its shareable link:')}", parse_mode='HTML', reply_markup=InlineKeyboardMarkup(buttons))
        return ConversationHandler.END

    # GET DIRECT SHARE LINK
    elif data.startswith("getlink_"):
        fid = data.split("_")[1]
        if fid in files_db:
            bot_info = await context.bot.get_me()
            share_url = f"https://t.me/{bot_info.username}?start={fid}"
            f_name = files_db[fid].get("name", "File")

            reply_msg = (
                f"{E_PARTY} {bold_sc('Here is your shareable link!')}\n\n"
                f"{E_CLIP} {bold_sc('File Title')}: <b>{f_name}</b>\n"
                f"{E_PIN} {bold_sc('Direct Access Link')}:\n<code>{share_url}</code>"
            )
            await query.edit_message_text(reply_msg, parse_mode='HTML', reply_markup=get_back_keyboard())
        else:
            await query.edit_message_text(f"{E_MEMO} {bold_sc('File not found!')}", parse_mode='HTML', reply_markup=get_back_keyboard())
        return ConversationHandler.END

    # --- NORMAL USER PERSONAL FJ CHANNEL CONTROLS ---
    elif data == "user_add_ch":
        await query.edit_message_text(
            f"{E_MEGAPHONE} {bold_sc('Send your Channel Username (e.g. @MyChannel) or ID (e.g. -100xxxxxx):')}\n\n"
            f"<i>{bold_sc('Note: Bot must be Admin in your channel to verify users!')}</i>",
            parse_mode='HTML',
            reply_markup=get_back_keyboard()
        )
        return WAITING_USER_CHANNEL_ADD

    elif data == "user_list_ch":
        u_chs = user_channels.get(user_id, [])
        if not u_chs:
            await query.edit_message_text(f"{E_MEMO} {bold_sc('You have not added any personal Force-Join channels!')}", parse_mode='HTML', reply_markup=get_back_keyboard())
            return ConversationHandler.END

        msg = f"{E_PIN} {bold_sc('Your Added Force-Join Channels:')}\n\n"
        for idx, ch in enumerate(u_chs, 1):
            msg += f"<b>{idx}.</b> <code>{ch}</code>\n"
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=get_back_keyboard())
        return ConversationHandler.END

    elif data == "user_rem_ch_menu":
        u_chs = user_channels.get(user_id, [])
        if not u_chs:
            await query.edit_message_text(f"{E_MEMO} {bold_sc('You have no personal channels to remove!')}", parse_mode='HTML', reply_markup=get_back_keyboard())
            return ConversationHandler.END

        buttons = []
        for idx, ch in enumerate(u_chs):
            buttons.append([InlineKeyboardButton(
                text=sc(f"Remove {ch}"), 
                callback_data=f"deluch_{idx}", 
                style="danger", 
                icon_custom_emoji_id="5870568528049868382"
            )])
        buttons.append([InlineKeyboardButton(text=sc('Back to Menu'), callback_data="main_menu", style="primary", icon_custom_emoji_id="5429651785352501917")])

        await query.edit_message_text(f"{E_MEGAPHONE} {bold_sc('Select your channel to remove:')}", parse_mode='HTML', reply_markup=InlineKeyboardMarkup(buttons))
        return ConversationHandler.END

    elif data.startswith("deluch_"):
        idx = int(data.split("_")[1])
        u_chs = user_channels.get(user_id, [])
        if 0 <= idx < len(u_chs):
            removed_ch = u_chs.pop(idx)
            await query.edit_message_text(f"{E_CHECK} {bold_sc('Your Channel')} <code>{removed_ch}</code> {bold_sc('Removed!')}", parse_mode='HTML', reply_markup=get_back_keyboard())
        return ConversationHandler.END

    # --- ADMIN / OWNER GLOBAL CONTROLS ---
    elif data == "admin_add_ch":
        if user_id not in admins:
            return ConversationHandler.END
        await query.edit_message_text(f"{E_MEGAPHONE} {bold_sc('Send Global Channel Username or ID:')}", parse_mode='HTML', reply_markup=get_back_keyboard())
        return WAITING_ADMIN_CHANNEL_ADD

    elif data == "admin_list_ch":
        if user_id not in admins:
            return ConversationHandler.END
        if not global_channels:
            await query.edit_message_text(f"{E_MEMO} {bold_sc('No Global Force-Join channels added yet!')}", parse_mode='HTML', reply_markup=get_back_keyboard())
            return ConversationHandler.END

        msg = f"{E_PIN} {bold_sc('Global Force-Join Channels List:')}\n\n"
        for idx, ch in enumerate(global_channels, 1):
            msg += f"<b>{idx}.</b> <code>{ch}</code>\n"
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=get_back_keyboard())
        return ConversationHandler.END

    elif data == "admin_rem_ch_menu":
        if user_id not in admins:
            return ConversationHandler.END
        if not global_channels:
            await query.edit_message_text(f"{E_MEMO} {bold_sc('No Global Force-Join channels to remove!')}", parse_mode='HTML', reply_markup=get_back_keyboard())
            return ConversationHandler.END

        buttons = []
        for idx, ch in enumerate(global_channels):
            buttons.append([InlineKeyboardButton(
                text=sc(f"Remove {ch}"), 
                callback_data=f"delgch_{idx}", 
                style="danger", 
                icon_custom_emoji_id="5870568528049868382"
            )])
        buttons.append([InlineKeyboardButton(text=sc('Back to Menu'), callback_data="main_menu", style="primary", icon_custom_emoji_id="5429651785352501917")])

        await query.edit_message_text(f"{E_MEGAPHONE} {bold_sc('Select Global Channel to Remove:')}", parse_mode='HTML', reply_markup=InlineKeyboardMarkup(buttons))
        return ConversationHandler.END

    elif data.startswith("delgch_"):
        if user_id not in admins:
            return ConversationHandler.END
        idx = int(data.split("_")[1])
        if 0 <= idx < len(global_channels):
            removed_ch = global_channels.pop(idx)
            await query.edit_message_text(f"{E_CHECK} {bold_sc('Global Channel')} <code>{removed_ch}</code> {bold_sc('Removed!')}", parse_mode='HTML', reply_markup=get_back_keyboard())
        return ConversationHandler.END

    elif data == "admin_add_admin":
        if user_id != OWNER_ID:
            return ConversationHandler.END
        await query.edit_message_text(f"{E_CROWN} {bold_sc('Send User ID of new Admin:')}", parse_mode='HTML', reply_markup=get_back_keyboard())
        return WAITING_ADMIN_ADD

    elif data == "admin_list_admin":
        if user_id != OWNER_ID:
            return ConversationHandler.END
        text = f"{E_CROWN} {bold_sc('Authorized Admins List')}:\n\n"
        for adm in admins:
            role = bold_sc("Owner") if adm == OWNER_ID else bold_sc("Admin")
            text += f"• <code>{adm}</code> ({role})\n"
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=get_back_keyboard())
        return ConversationHandler.END

    elif data == "admin_rem_admin_menu":
        if user_id != OWNER_ID:
            return ConversationHandler.END
        removable_admins = [a for a in admins if a != OWNER_ID]
        if not removable_admins:
            await query.edit_message_text(f"{E_MEMO} {bold_sc('No admins available to remove!')}", parse_mode='HTML', reply_markup=get_back_keyboard())
            return ConversationHandler.END

        buttons = []
        for adm in removable_admins:
            buttons.append([InlineKeyboardButton(
                text=sc(f"Remove {adm}"), 
                callback_data=f"deladm_{adm}", 
                style="danger", 
                icon_custom_emoji_id="5303040006347046717"
            )])
        buttons.append([InlineKeyboardButton(text=sc('Back to Menu'), callback_data="main_menu", style="primary", icon_custom_emoji_id="5429651785352501917")])

        await query.edit_message_text(f"{E_CROWN} {bold_sc('Select Admin to Remove:')}", parse_mode='HTML', reply_markup=InlineKeyboardMarkup(buttons))
        return ConversationHandler.END

    elif data.startswith("deladm_"):
        if user_id != OWNER_ID:
            return ConversationHandler.END
        adm_id = int(data.split("_")[1])
        if adm_id in admins and adm_id != OWNER_ID:
            admins.remove(adm_id)
            await query.edit_message_text(f"{E_CHECK} {bold_sc('Admin')} <code>{adm_id}</code> {bold_sc('Removed!')}", parse_mode='HTML', reply_markup=get_back_keyboard())
        return ConversationHandler.END

    elif data == "admin_broadcast":
        if user_id not in admins:
            return ConversationHandler.END
        await query.edit_message_text(f"{E_MEGAPHONE} {bold_sc('Send message text to broadcast to all users:')}", parse_mode='HTML', reply_markup=get_back_keyboard())
        return WAITING_BROADCAST

# --- CONVERSATION HANDLERS ---
async def process_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type != "private":
        return ConversationHandler.END

    user_id = update.effective_user.id
    msg = update.message

    if not await check_user_subscribed(context.bot, user_id, global_channels):
        await send_force_join_msg(update, context, user_id, global_channels)
        return ConversationHandler.END

    file_id, file_type, file_name = None, None, "File"

    if msg.document:
        file_id = msg.document.file_id
        file_type = "document"
        file_name = msg.document.file_name or "Document"
    elif msg.photo:
        file_id = msg.photo[-1].file_id
        file_type = "photo"
        file_name = "Photo"
    elif msg.video:
        file_id = msg.video.file_id
        file_type = "video"
        file_name = msg.video.file_name or "Video"
    elif msg.audio:
        file_id = msg.audio.file_id
        file_type = "audio"
        file_name = msg.audio.file_name or "Audio"

    if file_id:
        unique_key = str(uuid.uuid4())[:8]
        files_db[unique_key] = {
            "file_id": file_id,
            "type": file_type,
            "owner": user_id,
            "name": file_name
        }
        bot_info = await context.bot.get_me()
        share_link = f"https://t.me/{bot_info.username}?start={unique_key}"

        reply_txt = (
            f"{E_CHECK} {bold_sc('File Uploaded Successfully!')}\n\n"
            f"{E_CLIP} {bold_sc('File Title')}: <b>{file_name}</b>\n"
            f"{E_PIN} {bold_sc('Unique Key')}: <code>{unique_key}</code>\n\n"
            f"{E_PARTY} {bold_sc('Your Share Link')}:\n<code>{share_link}</code>"
        )
        await msg.reply_html(reply_txt, reply_markup=get_back_keyboard())
    else:
        await msg.reply_html(f"{E_MEMO} {bold_sc('Invalid file. Please send Document, Photo, Video, or Audio.')}", reply_markup=get_back_keyboard())
    return ConversationHandler.END

async def process_add_user_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type != "private":
        return ConversationHandler.END

    user_id = update.effective_user.id
    ch = update.message.text.strip()

    if user_id not in user_channels:
        user_channels[user_id] = []

    if ch not in user_channels[user_id]:
        user_channels[user_id].append(ch)
        await update.message.reply_html(
            f"{E_CHECK} {bold_sc('Personal Force-Join Channel Added!')}\n\n"
            f"{E_PIN} <code>{ch}</code>\n\n"
            f"<i>{bold_sc('Now users downloading your files must join this channel!')}</i>",
            reply_markup=get_back_keyboard()
        )
    else:
        await update.message.reply_html(f"{E_MEMO} {bold_sc('This channel is already added in your list.')}", reply_markup=get_back_keyboard())
    return ConversationHandler.END

async def process_add_admin_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type != "private":
        return ConversationHandler.END

    ch = update.message.text.strip()
    if ch not in global_channels:
        global_channels.append(ch)
        await update.message.reply_html(f"{E_CHECK} {bold_sc('Global Force-Join Channel Added!')}\n\n{E_PIN} <code>{ch}</code>", reply_markup=get_back_keyboard())
    else:
        await update.message.reply_html(f"{E_MEMO} {bold_sc('Channel already exists in global list.')}", reply_markup=get_back_keyboard())
    return ConversationHandler.END

async def process_add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type != "private":
        return ConversationHandler.END

    try:
        new_admin = int(update.message.text.strip())
        admins.add(new_admin)
        await update.message.reply_html(f"{E_CHECK} {bold_sc('New Admin Added Successfully!')}", reply_markup=get_back_keyboard())
    except ValueError:
        await update.message.reply_html(f"{E_MEMO} {bold_sc('Invalid User ID format!')}", reply_markup=get_back_keyboard())
    return ConversationHandler.END

async def process_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type != "private":
        return ConversationHandler.END

    b_msg = update.message.text
    count = 0
    for uid in list(bot_users):
        try:
            await context.bot.send_message(chat_id=uid, text=f"{E_MEGAPHONE} <b>{b_msg}</b>", parse_mode='HTML')
            count += 1
        except Exception:
            pass
    await update.message.reply_html(f"{E_CHECK} {bold_sc('Broadcast sent to')} <b>{count}</b> {bold_sc('users!')}", reply_markup=get_back_keyboard())
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type != "private":
        return ConversationHandler.END

    await update.message.reply_html(bold_sc("Action Cancelled."), reply_markup=get_back_keyboard())
    return ConversationHandler.END

# --- BOT ENGINE SETUP ---
def main():
    request = HTTPXRequest(
        connect_timeout=60.0,
        read_timeout=60.0,
        write_timeout=60.0,
        pool_timeout=60.0
    )

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .request(request)
        .build()
    )

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler)],
        states={
            WAITING_FILE: [MessageHandler(filters.ALL & ~filters.COMMAND, process_file_upload)],
            WAITING_USER_CHANNEL_ADD: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_add_user_channel)],
            WAITING_ADMIN_CHANNEL_ADD: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_add_admin_channel)],
            WAITING_ADMIN_ADD: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_add_admin)],
            WAITING_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_broadcast)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(button_handler)
        ],
        per_message=False
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)

    print("Bot updated and running smoothly...")
    app.run_polling()

if __name__ == "__main__":
    main()
