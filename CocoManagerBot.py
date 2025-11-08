import logging
import os
import re
from functools import wraps
import datetime
import time 
from telegram import Update, ChatMemberAdministrator, ChatMemberOwner, ChatPermissions
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- 1. CONFIGURATION ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "8471321442:AAHxai89crCpcsjIelZfZfSM9lM83UwwXM4")
OWNER_ID = 8167780741 

# --- Database Placeholder ---
GROUP_SETTINGS = {
    -100123456789: {'url_lock': False, 'mutes': {}}, 
}
# --------------------------------------------------------------------------


# --- 2. CORE UTILITY FUNCTIONS (UNMODIFIED) ---

def owner_only(func):
    """Decorator to restrict a command to the owner only (in private chat)."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if update.effective_chat.type == 'private' and user_id != OWNER_ID:
            await update.message.reply_text(
                "🛑 **Unauthorized.** This is a private bot managed by its owner."
            )
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

def admin_only(func):
    """Decorator to restrict a command to group admins only."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id

        if update.effective_chat.type == 'private':
            await update.message.reply_text(
                "🛡️ This command must be used in a group or supergroup chat."
            )
            return
        
        member = await context.bot.get_chat_member(chat_id, user_id)
        is_admin = isinstance(member, (ChatMemberAdministrator, ChatMemberOwner))

        if not is_admin:
            await update.message.reply_text(
                "🚫 **Permission Denied.** You must be an administrator to use this command."
            )
            return
        
        return await func(update, context, *args, **kwargs)
    return wrapped

def parse_duration_to_timestamp(duration_str: str) -> int | None:
    """Parses duration string (e.g., '1h', '30m', '2d') to a future Unix timestamp."""
    match = re.fullmatch(r'(\d+)([mhd])', duration_str.lower())
    if not match:
        return None

    value, unit = match.groups()
    value = int(value)
    
    if unit == 'm':
        delta = datetime.timedelta(minutes=value)
    elif unit == 'h':
        delta = datetime.timedelta(hours=value)
    elif unit == 'd':
        delta = datetime.timedelta(days=value)
    else:
        return None

    current_time = int(time.time())
    total_seconds = int(delta.total_seconds())
    
    if total_seconds < 30:
        total_seconds = 30
    
    max_seconds = 366 * 86400
    if total_seconds > max_seconds:
        total_seconds = max_seconds
        
    return current_time + total_seconds

def chunk_list(input_list, chunk_size):
    """Yields successive n-sized chunks from input_list."""
    for i in range(0, len(input_list), chunk_size):
        yield input_list[i:i + chunk_size]

def get_mutes_list(chat_id: int) -> dict:
    """Retrieves or initializes the mutable mutes list for a chat, clearing expired ones."""
    if chat_id not in GROUP_SETTINGS:
        GROUP_SETTINGS[chat_id] = {'url_lock': False, 'mutes': {}}
    elif 'mutes' not in GROUP_SETTINGS[chat_id]:
        GROUP_SETTINGS[chat_id]['mutes'] = {}
    
    current_time = int(time.time())
    expired_users = [user_id for user_id, expiry in GROUP_SETTINGS[chat_id]['mutes'].items() 
                     if expiry is not None and expiry < current_time]
    
    for user_id in expired_users:
        del GROUP_SETTINGS[chat_id]['mutes'][user_id]
        
    return GROUP_SETTINGS[chat_id]['mutes']


# --- 3. COMMAND HANDLERS (NEW WELCOME & GREETING REPLY) ---

# --- NEW: Welcome Message Handler ---
async def welcome_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when new users join the chat."""
    for user in update.message.new_chat_members:
        # Check if the user is the bot itself (to avoid greeting itself)
        if user.id == context.bot.id:
            continue
            
        # Create a mention link for the new user
        user_mention = f"[{user.first_name}](tg://user?id={user.id})"
        
        welcome_message = f"👋 Welcome to Coco Zone, {user_mention}! Please read the rules and have fun. 😊"
        
        await update.message.reply_text(
            welcome_message,
            parse_mode='Markdown',
            # Optionally delete the system message (user joined the group)
            # await update.message.delete()
        )

# --- NEW: Greeting Reply Handler ---
async def reply_to_greetings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Replies to common greetings like hello, hi, hey, yo."""
    
    # Check if the message is from the bot itself (to prevent loops)
    if update.effective_user.id == context.bot.id:
        return
        
    # Simple reply
    await update.message.reply_text(f"Hello there, **{update.effective_user.first_name}**! Welcome to the chat. 🤗", parse_mode='Markdown')


# --- Fun Command ---
async def roll_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Rolls an animated die."""
    await update.message.reply_dice(emoji='🎲') 

# --- Other command handlers (help, warn, mute, etc.) remain in the script ---
@owner_only
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command with owner restriction."""
    chat_type = update.effective_chat.type

    if chat_type == 'private':
        await update.message.reply_text(
            f'Hello, **Owner ({OWNER_ID})**! Coco\'s Manager is ready. Use /help for commands.',
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            'Coco\'s Manager is active! Use /help to see my commands.'
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a help message listing all available commands (partial list)."""
    help_text = (
        "🥥 **Coco's Manager Commands:**\n\n"
        "**🎲 Fun:**\n"
        "`/roll` - Rolls an animated die (shows result 1-6).\n\n"
        "**🛡️ Moderation (Admin Only):**\n"
        "`/ban` - Bans the replied-to user.\n"
        "`/mute [duration]` - Mutes the replied-to user (e.g., `/mute 1h`).\n"
        "`/unmute` - Unmutes the replied-to user.\n"
        "`/allmuted` - Lists all currently muted users.\n"
        "`/unmuteall` - Unmutes all tracked users.\n"
        "`/warn [reason]` - Issues a warning to the replied-to user.\n\n"
        "**👥 Admin Tools:**\n"
        "`/promote`, `/demote` - Manage admin status.\n"
        "`/all [message]` - Tags all group administrators in chunks.\n"
        "`/lock url`, `/unlock url` - Manage anti-spam locks.\n\n"
        "**ℹ️ Info:**\n"
        "`/id`, `/help`."
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

@admin_only
async def warn_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Issues a warning, including a reason if provided."""
    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to a user's message to issue a warning.")
        return

    target_user = update.message.reply_to_message.from_user
    reason = " ".join(context.args) if context.args else "No reason specified."
    
    await update.message.reply_text(
        f"⚠️ Warning issued to **{target_user.first_name}**.\n"
        f"**Reason:** {reason}\n"
        f"(This warning is currently NOT stored in a database.)",
        parse_mode='Markdown'
    )

@admin_only
async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mutes a user by restricting their permissions, optionally for a duration, and tracks it."""
    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to a user's message to mute them.")
        return

    target_user = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id

    duration_str = context.args[0] if context.args else None
    until_date = None
    mute_message = "permanently"
    mute_expiry_timestamp = None

    if duration_str:
        mute_expiry_timestamp = parse_duration_to_timestamp(duration_str)
        if mute_expiry_timestamp is None:
            await update.message.reply_text("❌ Invalid duration format. Use: `/mute <time><unit>`. E.g., `/mute 1h`, `/mute 30m`, `/mute 1d`.", parse_mode='Markdown')
            return
        
        until_date = mute_expiry_timestamp
        mute_message = f"for **{duration_str}**"

    try:
        bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
        if not bot_member.can_restrict_members:
             await update.message.reply_text("❌ Failed to mute user. I need the 'Ban Users' admin right to restrict permissions.")
             return

        permissions = ChatPermissions() 
        await context.bot.restrict_chat_member(
            chat_id,
            target_user.id,
            permissions=permissions,
            until_date=until_date
        )
        
        # Store name along with expiry
        full_name = target_user.first_name + (f" {target_user.last_name}" if target_user.last_name else "")
        mutes = get_mutes_list(chat_id)
        mutes[target_user.id] = {'expiry': mute_expiry_timestamp, 'name': full_name}

        await update.message.reply_text(
            f"🔇 Muted user: **{target_user.first_name}** {mute_message}. They can no longer send messages.",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error muting user: {e}")
        await update.message.reply_text("❌ Failed to mute user. Make sure I have sufficient admin permissions and the target is not a higher-ranking admin.")

@admin_only
async def unmute_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unmutes a user by restoring their default permissions and clears tracking status."""
    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to a user's message to unmute them.")
        return

    target_user = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id

    try:
        bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
        if not bot_member.can_restrict_members:
             await update.message.reply_text("❌ Failed to unmute user. I need the 'Ban Users' admin right to restore permissions.")
             return

        permissions = ChatPermissions(
            can_send_messages=True, can_send_media_messages=True, can_send_polls=True, 
            can_send_other_messages=True, can_add_web_page_previews=True
        )
        await context.bot.restrict_chat_member(
            chat_id,
            target_user.id,
            permissions=permissions
        )
        
        mutes = get_mutes_list(chat_id)
        if target_user.id in mutes:
            del mutes[target_user.id]

        await update.message.reply_text(
            f"🔊 Unmuted user: **{target_user.first_name}**. They can now send messages again.",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error unmuting user: {e}")
        await update.message.reply_text("❌ Failed to unmute user. Ensure the user was restricted by the bot.")

@admin_only
async def all_muted_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lists all actively muted users tracked by the bot (using stored names)."""
    chat_id = update.effective_chat.id
    muted_users = get_mutes_list(chat_id)
    
    if not muted_users:
        await update.message.reply_text("✅ There are currently no users muted by Coco's Manager in this chat.")
        return

    message_text = "🔇 **Currently Muted Users:**\n"
    current_time = int(time.time())
    
    # Iterate through stored mute info, not calling API
    for user_id, mute_info in muted_users.items():
        name = mute_info.get('name', f"Unknown User ({user_id})")
        expiry = mute_info.get('expiry')
        
        if expiry is None:
            expiry_str = "Permanent"
        else:
            dt = datetime.datetime.fromtimestamp(expiry)
            time_left = dt - datetime.datetime.fromtimestamp(current_time)
            
            hours, remainder = divmod(time_left.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            
            expiry_str = f"Expires in: {time_left.days}d {hours}h {minutes}m"

        message_text += f"• **{name}** (`{user_id}`): {expiry_str}\n"

    await update.message.reply_text(message_text, parse_mode='Markdown')

@admin_only
async def unmute_all_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unmutes all users currently tracked as muted by the bot."""
    chat_id = update.effective_chat.id
    muted_users = get_mutes_list(chat_id).copy()
    
    if not muted_users:
        await update.message.reply_text("✅ No users are currently tracked as muted by the bot.")
        return

    success_count = 0
    permissions = ChatPermissions(
        can_send_messages=True, can_send_media_messages=True, can_send_polls=True, 
        can_send_other_messages=True, can_add_web_page_previews=True
    )
    
    for user_id in muted_users.keys():
        try:
            await context.bot.restrict_chat_member(chat_id, user_id, permissions=permissions)
            
            if user_id in GROUP_SETTINGS[chat_id]['mutes']:
                del GROUP_SETTINGS[chat_id]['mutes'][user_id]
                success_count += 1
                
        except Exception as e:
            logger.error(f"Failed to unmute user {user_id}: {e}")
            pass

    await update.message.reply_text(f"✅ Successfully unmuted **{success_count}** user(s). The mute tracking list has been cleared.", parse_mode='Markdown')

@admin_only
async def all_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tags all administrators in chunks for better notification reliability."""
    chat_id = update.effective_chat.id
    
    try:
        admin_members = await context.bot.get_chat_administrators(chat_id)
        mention_list = []
        
        for member in admin_members:
            if member.user.id == context.bot.id:
                continue
            mention = f"[{member.user.first_name}](tg://user?id={member.user.id})"
            mention_list.append(mention)

        if not mention_list:
            await update.message.reply_text("There are no administrators to tag in this chat.")
            return
            
        tag_message = " ".join(context.args) if context.args else "🚨 **ATTENTION ADMINS**"
        
        MENTION_CHUNK_SIZE = 5 
        mention_chunks = list(chunk_list(mention_list, MENTION_CHUNK_SIZE))

        await update.message.reply_text(
            tag_message,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )

        for chunk in mention_chunks:
            chunk_message = " ".join(chunk)
            await context.bot.send_message( 
                chat_id,
                chunk_message,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
        
    except Exception as e:
        logger.error(f"Error tagging all: {e}")
        await update.message.reply_text("❌ Failed to tag administrators. Check the bot's permissions.")

@admin_only
async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Bans a user, similar to /ban."""
    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to a user's message to ban them.")
        return
    target_user = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id
    try:
        bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
        if not bot_member.can_restrict_members:
             await update.message.reply_text("❌ Failed to ban user. I need the 'Ban Users' admin right.")
             return
        await context.bot.ban_chat_member(chat_id, target_user.id)
        await update.message.reply_text(
            f"🔨 Banned user: **{target_user.first_name}** (`{target_user.id}`).",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error banning user: {e}")
        await update.message.reply_text("❌ Failed to ban user. Make sure I have sufficient admin permissions and the target is not a higher-ranking admin.")

@admin_only
async def promote_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Promotes a user to a regular administrator."""
    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to a user's message to promote them.")
        return
    target_user = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id
    try:
        bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
        if not bot_member.can_promote_members:
            await update.message.reply_text("❌ Failed to promote user. I need the 'Add New Admins' admin right.")
            return
        await context.bot.promote_chat_member(
            chat_id, target_user.id, can_delete_messages=True, can_restrict_members=True, can_invite_users=True, can_pin_messages=True
        )
        await update.message.reply_text(
            f"👑 Promoted **{target_user.first_name}** to Administrator.",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error promoting user: {e}")
        await update.message.reply_text("❌ Failed to promote user. I might not have the 'Add New Admins' right, or the target is a creator/owner.")

@admin_only
async def demote_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Demotes an administrator back to a regular member."""
    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to an admin's message to demote them.")
        return
    target_user = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id
    if target_user.id == context.bot.id:
        await update.message.reply_text("I cannot demote myself. Please demote me manually.")
        return
    try:
        bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
        if not bot_member.can_promote_members:
            await update.message.reply_text("❌ Failed to demote user. I need the 'Add New Admins' admin right.")
            return
        await context.bot.promote_chat_member(
            chat_id, target_user.id, can_change_info=False, can_delete_messages=False, can_invite_users=False,
            can_restrict_members=False, can_pin_messages=False, can_promote_members=False,
        )
        await update.message.reply_text(
            f"🔻 Demoted **{target_user.first_name}** to a regular member.",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error demoting user: {e}")
        await update.message.reply_text("❌ Failed to demote user. I might not have the 'Add New Admins' right, or the target is a creator/owner or a higher-ranking admin.")

@admin_only
async def lock_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Implements the /lock command logic."""
    if not context.args:
        await update.message.reply_text("Usage: `/lock <type>`. E.g., `/lock url`", parse_mode='Markdown')
        return
    lock_type = context.args[0].lower()
    chat_id = update.effective_chat.id
    if chat_id not in GROUP_SETTINGS:
        GROUP_SETTINGS[chat_id] = {'url_lock': False, 'mutes': {}}
    if lock_type == 'url':
        GROUP_SETTINGS[chat_id]['url_lock'] = True
        await update.message.reply_text("🔒 **URL Lock** activated! Messages containing links will now be deleted.", parse_mode='Markdown')
    else:
        await update.message.reply_text(f"Unknown lock type: `{lock_type}`. Available: `url`.", parse_mode='Markdown')

@admin_only
async def unlock_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Implements the /unlock command logic."""
    if not context.args:
        await update.message.reply_text("Usage: `/unlock <type>`. E.g., `/unlock url`", parse_mode='Markdown')
        return
    unlock_type = context.args[0].lower()
    chat_id = update.effective_chat.id
    if chat_id not in GROUP_SETTINGS:
        await update.message.reply_text("No locks are configured for this group.")
        return
    if unlock_type == 'url':
        GROUP_SETTINGS[chat_id]['url_lock'] = False
        await update.message.reply_text("🔓 **URL Lock** deactivated! Links are now allowed.", parse_mode='Markdown')
    else:
        await update.message.reply_text(f"Unknown lock type: `{unlock_type}`. Available: `url`.", parse_mode='Markdown')

async def anti_url_spam_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """MessageHandler that deletes messages containing links if URL lock is active."""
    if not update.message or not update.message.text: return
    chat_id = update.effective_chat.id
    message_text = update.message.text
    is_url_locked = GROUP_SETTINGS.get(chat_id, {}).get('url_lock', False)
    if is_url_locked:
        url_pattern = re.compile(r'https?://|www\.', re.IGNORECASE)
        if url_pattern.search(message_text):
            try:
                await update.message.delete()
                await context.bot.send_message(
                    chat_id, f"🛑 **Link deleted!** URLs are not allowed here.", parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Failed to delete message: {e}")

async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gets the user or chat ID."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    response = f"👤 **Your User ID:** `{user_id}`"
    if chat_type != 'private':
        response += f"\n🏠 **Chat ID:** `{chat_id}`"
    await update.message.reply_text(response, parse_mode='Markdown')

# --- 4. MAIN FUNCTION ---

def main() -> None:
    """Start the bot."""
    application = Application.builder().token(BOT_TOKEN).build()

    # --- ADD WELCOME & GREETING HANDLERS FIRST ---
    # 1. New Member Welcome
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_members))
    
    # 2. Greeting Auto-Reply (Must be placed before the anti-spam handler)
    greeting_pattern = re.compile(r'^(hello|hi|hey|yo)[\s\S]*$', re.IGNORECASE)
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(greeting_pattern), reply_to_greetings))
    
    # --- COMMAND HANDLERS ---
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("id", id_command))
    application.add_handler(CommandHandler("roll", roll_command)) 
    
    # Moderation & Locks (Admin Only)
    application.add_handler(CommandHandler("ban", ban_command))
    application.add_handler(CommandHandler("mute", mute_command)) 
    application.add_handler(CommandHandler("unmute", unmute_command)) 
    application.add_handler(CommandHandler("warn", warn_command)) 
    application.add_handler(CommandHandler("promote", promote_command))
    application.add_handler(CommandHandler("demote", demote_command))
    application.add_handler(CommandHandler("lock", lock_command))
    application.add_handler(CommandHandler("unlock", unlock_command))
    application.add_handler(CommandHandler("all", all_command)) 
    application.add_handler(CommandHandler("allmuted", all_muted_command)) 
    application.add_handler(CommandHandler("unmuteall", unmute_all_command)) 
    
    # --- MESSAGE HANDLERS (Anti-Spam Logic) ---
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, anti_url_spam_handler))
    
    logger.info("Coco's Manager is starting...")

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
