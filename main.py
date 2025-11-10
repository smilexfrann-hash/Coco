import logging
import os
import re
from functools import wraps
import datetime
import time 
from telegram import Update, ChatMemberAdministrator, ChatMemberOwner, ChatPermissions
from telegram import InlineKeyboardButton, InlineKeyboardMarkup 
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes, 
    CallbackQueryHandler
)
from telegram.error import NetworkError 

# --- 1. CONFIGURATION ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- USER-PROVIDED CREDENTIALS (Ready to run) ---
BOT_TOKEN = "8471321442:AAHxai89crCpcsjIelZfZfSM9lM83UwwXM4"
OWNER_ID = 8167780741
# -----------------------------------

# --- Database Placeholder (Simulates Persistent Storage) ---
GROUP_SETTINGS = {
    -100123456789: {'url_lock': False, 'mutes': {}, 'warnings': {}, 'warn_limit': 3}, 
}
# --------------------------------------------------------------------------


# --- 2. CORE UTILITY FUNCTIONS ---

def owner_only(func):
    """Decorator to restrict a command to the hardcoded owner ID only."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id != OWNER_ID:
            await update.message.reply_text(
                "🛑 **Access Denied.** Only the bot owner can use this command.",
                parse_mode='Markdown'
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

def get_chat_data(chat_id: int) -> dict:
    """Retrieves or initializes the full chat data structure, including warnings."""
    if chat_id not in GROUP_SETTINGS:
        GROUP_SETTINGS[chat_id] = {'url_lock': False, 'mutes': {}, 'warnings': {}, 'warn_limit': 3}
    if 'warnings' not in GROUP_SETTINGS[chat_id]:
        GROUP_SETTINGS[chat_id]['warnings'] = {}
    if 'warn_limit' not in GROUP_SETTINGS[chat_id]:
        GROUP_SETTINGS[chat_id]['warn_limit'] = 3
    return GROUP_SETTINGS[chat_id]

def parse_duration_to_timestamp(duration_str: str) -> int | None:
    """Parses duration string (e.g., '1h', '30m', '2d') to a future Unix timestamp."""
    match = re.fullmatch(r'(\d+)([mhd])', duration_str.lower())
    if not match: return None
    value, unit = match.groups(); value = int(value)
    delta = datetime.timedelta(minutes=value) if unit == 'm' else (datetime.timedelta(hours=value) if unit == 'h' else datetime.timedelta(days=value))
    total_seconds = int(delta.total_seconds())
    return int(time.time()) + (total_seconds if total_seconds >= 30 else 30)

def chunk_list(input_list, chunk_size):
    """Yields successive n-sized chunks from input_list."""
    for i in range(0, len(input_list), chunk_size): yield input_list[i:i + chunk_size]

def get_mutes_list(chat_id: int) -> dict:
    """Retrieves the mutable mutes list for a chat, clearing expired ones."""
    chat_data = get_chat_data(chat_id)
    current_time = int(time.time())
    expired_users = [user_id for user_id, expiry in chat_data['mutes'].items() 
                     if expiry is not None and expiry < current_time]
    for user_id in expired_users: del chat_data['mutes'][user_id]
    return chat_data['mutes']

async def check_target_admin_status(chat_id, user_id, context) -> bool:
    """Checks if the target user is an admin or owner in the chat."""
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return isinstance(member, (ChatMemberAdministrator, ChatMemberOwner))
    except Exception:
        return False


# --- 3. HANDLERS AND COMMANDS ---

# --- Status Update Handlers and Base Commands (Unmodified) ---
async def welcome_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when new users join the chat."""
    for user in update.message.new_chat_members:
        if user.id == context.bot.id: continue
        user_mention = f"[{user.first_name}](tg://user?id={user.id})"
        welcome_message = f"👋 Welcome to Coco Zone, {user_mention}! Please read the rules and have fun. 😊"
        await update.message.reply_text(
            welcome_message,
            parse_mode='Markdown',
        )

async def reply_to_greetings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Replies to common greetings like hello, hi, hey, yo."""
    if update.effective_user.id == context.bot.id: return
    await update.message.reply_text(f"Hello there, **{update.effective_user.first_name}**! Welcome to the chat. 🤗", parse_mode='Markdown')

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
        "**⭐ Quick Mod:**\n"
        "`/mod` or `/m` - Reply to a user to open the inline moderation panel.\n\n"
        "**🎲 Fun:**\n"
        "`/roll` - Rolls an animated die (shows result 1-6).\n\n"
        "**🛡️ Warning Management (Admin Only):**\n"
        "`/warn [reason]` - Issues a warning.\n"
        "`/rwarn` - Removes 1 warning (reply or ID).\n"
        "`/allwarn` - Shows list of all warned users.\n"
        "`/rallwarn` - Clears all warnings in the chat.\n"
        "`/setwarnlimit <num>` - Set the number of warnings before a permanent mute (Default: 3).\n\n"
        "**👥 Moderation/Tools:**\n"
        "`/ban`, `/unban`, `/mute`, `/unmute` - (Also usable via /mod).\n"
        "`/allmuted`, `/unmuteall` - Manage mutes.\n"
        "`/promote`, `/demote`, `/all [message]` - Admin tools.\n"
        "`/lock url`, `/unlock url` - Manage anti-spam locks.\n\n"
        "**ℹ️ Info:**\n"
        "`/id`, `/help`."
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def roll_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Rolls an animated die."""
    await update.message.reply_dice(emoji='🎲') 

async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gets the user or chat ID."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    chat_type = update.effective_chat.type
    response = f"👤 **Your User ID:** `{user_id}`"
    if chat_type != 'private':
        response += f"\n🏠 **Chat ID:** `{chat_id}`"
    await update.message.reply_text(response, parse_mode='Markdown')

# --- Warning Management Commands ---
@admin_only
async def set_warn_limit_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sets the maximum number of warnings before a permanent mute."""
    if not context.args or not context.args[0].isdigit():
        chat_data = get_chat_data(update.effective_chat.id)
        current_limit = chat_data['warn_limit']
        await update.message.reply_text(
            f"Usage: `/setwarnlimit <number>`. Current limit is **{current_limit}**.",
            parse_mode='Markdown'
        )
        return

    try:
        new_limit = int(context.args[0])
        if new_limit < 1:
            await update.message.reply_text("The warning limit must be at least 1.")
            return

        chat_data = get_chat_data(update.effective_chat.id)
        chat_data['warn_limit'] = new_limit
        await update.message.reply_text(
            f"✅ Warning limit successfully set to **{new_limit}**.",
            parse_mode='Markdown'
        )
    except Exception:
        await update.message.reply_text("❌ Could not set warning limit. Please use a whole number.")

@admin_only
async def warn_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Issues a warning, increments count, and enforces permanent mute limit."""
    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to a user's message to issue a warning.")
        return

    target_user = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id
    
    if await check_target_admin_status(chat_id, target_user.id, context):
        await update.message.reply_text(
            f"🚫 Cannot warn **{target_user.first_name}**: They are an administrator or the group creator.",
            parse_mode='Markdown'
        )
        return

    chat_data = get_chat_data(chat_id)
    
    current_count = chat_data['warnings'].get(target_user.id, 0)
    if not isinstance(current_count, int): current_count = 0 
         
    new_count = current_count + 1
    warn_limit = chat_data['warn_limit']
    
    reason = " ".join(context.args) if context.args else "No reason specified."

    if new_count >= warn_limit:
        # EXECUTE PERMANENT MUTE
        try:
            permissions = ChatPermissions()
            await context.bot.restrict_chat_member(chat_id, target_user.id, permissions=permissions)
            
            full_name = target_user.first_name + (f" {target_user.last_name}" if target_user.last_name else "")
            mutes = get_mutes_list(chat_id)
            mutes[target_user.id] = {'expiry': None, 'name': full_name}

            chat_data['warnings'][target_user.id] = 0
            
            await update.message.reply_text(
                f"🚨 **Final Warning!** User **{target_user.first_name}** hit the limit of {warn_limit} warnings and has been **PERMANENTLY MUTED**.\n"
                f"Reason: {reason}",
                parse_mode='Markdown'
            )
            return
        except Exception:
            await update.message.reply_text("❌ Failed to enforce mute. Please check bot's permissions (Ban Users right is required).", parse_mode='Markdown')
            return
    else:
        # ISSUE WARNING
        chat_data['warnings'][target_user.id] = new_count
        
        await update.message.reply_text(
            f"⚠️ Warning issued to **{target_user.first_name}**.\n"
            f"**Count:** {new_count} of {warn_limit}\n"
            f"**Reason:** {reason}",
            parse_mode='Markdown'
        )

@admin_only
async def remove_warn_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Removes one warning from a user, supporting replies or IDs."""
    chat_id = update.effective_chat.id
    target_user = None
    
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
    elif context.args and context.args[0].isdigit():
        try:
            target_user_id = int(context.args[0])
            target_user = (await context.bot.get_chat_member(chat_id, target_user_id)).user
        except Exception:
            await update.message.reply_text("❌ Invalid user ID provided.", parse_mode='Markdown')
            return
    else:
        await update.message.reply_text("Please reply to a user's message or provide their User ID to remove a warning.")
        return

    chat_data = get_chat_data(chat_id)
    target_user_id = target_user.id
    current_count = chat_data['warnings'].get(target_user.id, 0)
    
    if current_count <= 0:
        await update.message.reply_text(f"✅ **{target_user.first_name}** has no active warnings to remove.", parse_mode='Markdown')
        return

    new_count = current_count - 1
    chat_data['warnings'][target_user_id] = new_count

    await update.message.reply_text(
        f"✅ Removed 1 warning from **{target_user.first_name}**.\n"
        f"New warning count: **{new_count}**.",
        parse_mode='Markdown'
    )

@admin_only
async def all_warn_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows a list of all persons with active warnings."""
    chat_id = update.effective_chat.id
    chat_data = get_chat_data(chat_id)
    warned_users = {uid: count for uid, count in chat_data['warnings'].items() if count > 0}

    if not warned_users:
        await update.message.reply_text("✅ No users currently have active warnings in this chat.")
        return

    message_parts = ["⚠️ **Users with Active Warnings:**"]
    warn_limit = chat_data['warn_limit']

    for user_id, count in sorted(warned_users.items(), key=lambda item: item[1], reverse=True):
        try:
            user = await context.bot.get_chat_member(chat_id, user_id)
            name = user.user.first_name
        except Exception:
            name = f"Unknown User ({user_id})"

        message_parts.append(f"• **{name}**: {count} of {warn_limit}")

    await update.message.reply_text("\n".join(message_parts), parse_mode='Markdown')

@admin_only
async def remove_all_warn_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Removes all warnings from all persons in the chat."""
    chat_data = get_chat_data(update.effective_chat.id)
    warned_count = len([uid for uid, count in chat_data['warnings'].items() if count > 0])
    
    if not warned_count:
        await update.message.reply_text("✅ No active warnings found to remove.")
        return

    chat_data['warnings'] = {}
    
    await update.message.reply_text(
        f"✅ Successfully cleared **all {warned_count} active warnings** from all users in this chat.",
        parse_mode='Markdown'
    )

# --- Moderation & Utility Commands ---
@admin_only
async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mutes a user by restricting their permissions, optionally for a duration, and tracks it."""
    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to a user's message to mute them.")
        return

    target_user = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id

    # FIX: Check Hierarchy here to prevent generic failure
    if await check_target_admin_status(chat_id, target_user.id, context):
        await update.message.reply_text(
            f"🚫 Cannot mute **{target_user.first_name}**: They are an administrator or the group creator.",
            parse_mode='Markdown'
        )
        return

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
        # Check if user is ALREADY muted (for idempotent success message)
        target_member = await context.bot.get_chat_member(chat_id, target_user.id)
        if not target_member.can_send_messages and until_date is None:
            await update.message.reply_text(f"✅ User **{target_user.first_name}** is already permanently muted.", parse_mode='Markdown')
            return

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
        
        # Success: Update local tracking
        full_name = target_user.first_name + (f" {target_user.last_name}" if target_user.last_name else "")
        mutes = get_mutes_list(chat_id)
        mutes[target_user.id] = {'expiry': mute_expiry_timestamp, 'name': full_name}

        await update.message.reply_text(
            f"✅ Muted user: **{target_user.first_name}** {mute_message}. They can no longer send messages.",
            parse_mode='Markdown'
        )
    
    # CATCH API ERROR AND TREAT AS SUCCESS IF USER IS ALREADY RESTRICTED
    except Exception as e:
        error_message = str(e)
        
        if "not a member" in error_message or "user is already restricted" in error_message or "chat member is not found" in error_message:
            # Treat this as an idempotent success for consistency
            await update.message.reply_text(f"✅ User **{target_user.first_name}** is already restricted (mute successful for consistency).", parse_mode='Markdown')
            
            # Ensure local tracking is updated as a positive outcome
            full_name = target_user.first_name + (f" {target_user.last_name}" if target_user.last_name else "")
            mutes = get_mutes_list(chat_id)
            mutes[target_user.id] = {'expiry': mute_expiry_timestamp, 'name': full_name}
            
        else:
            logger.error(f"Error muting user: {e}")
            await update.message.reply_text("❌ Failed to mute user. Make sure I have sufficient admin permissions and the target is not a higher-ranking admin.", parse_mode='Markdown')


@admin_only
async def unmute_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unmutes a user by restoring their default permissions and clears tracking status (Idempotent)."""
    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to a user's message to unmute them.")
        return

    target_user = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id

    try:
        # 1. Get the current status of the target user
        target_member = await context.bot.get_chat_member(chat_id, target_user.id)
        
        # Determine if the user is currently NOT restricted
        if target_member.can_send_messages and target_member.can_send_media_messages:
            # Report SUCCESS if they are already unmuted
            await update.message.reply_text(f"✅ User **{target_user.first_name}** is already unrestricted (unmuted).", parse_mode='Markdown')
            
            # Clean up local tracking regardless
            mutes = get_mutes_list(chat_id)
            if target_user.id in mutes:
                del mutes[target_user.id]
            return
            
        # 2. Proceed with Unmuting (since target_member.can_send_messages is False)
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
        
        # 3. Clean up tracking status after successful API call
        mutes = get_mutes_list(chat_id)
        if target_user.id in mutes:
            del mutes[target_user.id]

        await update.message.reply_text(
            f"🔊 Unmuted user: **{target_user.first_name}**. They can now send messages again.",
            parse_mode='Markdown'
        )
    except NetworkError as ne:
        logger.error(f"Network Error during unmute: {ne}")
        await update.message.reply_text("❌ Failed to unmute due to a **connection error**. Please try again or check stability.", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error unmuting user: {e}")
        await update.message.reply_text("❌ Failed to unmute user. An internal error occurred, or the user may already be fully unrestricted.", parse_mode='Markdown')

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
    """Bans a user, similar to /ban (Idempotent)."""
    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to a user's message to ban them.")
        return
    
    target_user = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id
    
    if await check_target_admin_status(chat_id, target_user.id, context):
        await update.message.reply_text(
            f"🚫 Cannot ban **{target_user.first_name}**: They are an administrator or the group creator.",
            parse_mode='Markdown'
        )
        return
        
    try:
        # Check status before attempting ban
        target_member = await context.bot.get_chat_member(chat_id, target_user.id)
        if target_member.status in ['kicked', 'left']:
            await update.message.reply_text(f"✅ User **{target_user.first_name}** is already banned.", parse_mode='Markdown')
            return

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
async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unbans a user, restoring membership status (Idempotent)."""
    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to a user's message to unban them.")
        return

    target_user = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id

    try:
        # Check status before attempting unban
        target_member = await context.bot.get_chat_member(chat_id, target_user.id)
        
        if target_member.status != 'kicked':
             await update.message.reply_text(f"✅ User **{target_user.first_name}** is not banned (already unrestricted).", parse_mode='Markdown')
             return

        bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
        if not bot_member.can_restrict_members:
             await update.message.reply_text("❌ Failed to unban user. I need the 'Ban Users' admin right.")
             return

        await context.bot.unban_chat_member(chat_id, target_user.id)
        
        await update.message.reply_text(
            f"🔓 Unbanned user: **{target_user.first_name}**. They can rejoin the chat.",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error unbanning user: {e}")
        await update.message.reply_text("❌ Failed to unban user. Ensure the user was recently banned or check bot permissions.")


@owner_only
async def promote_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Promotes a user to a regular administrator (OWNER ONLY)."""
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

@owner_only
async def demote_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Demotes an administrator back to a regular member (OWNER ONLY)."""
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
        GROUP_SETTINGS[chat_id] = {'url_lock': False, 'mutes': {}, 'warnings': {}, 'warn_limit': 3}
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
    is_url_locked = get_chat_data(chat_id).get('url_lock', False)
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

# --- Inline Moderation Handlers ---
@admin_only
async def mod_panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends an inline keyboard for moderation actions when replying to a message."""
    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to a user's message to open the moderation panel.")
        return
    
    target_user = update.message.reply_to_message.from_user
    target_user_id = target_user.id
    target_user_name = target_user.first_name
    
    keyboard = [
        [
            InlineKeyboardButton("🔨 Ban (Permanent)", callback_data=f'mod_ban_{target_user_id}'),
            InlineKeyboardButton("🔇 Mute (Permanent)", callback_data=f'mod_mute_{target_user_id}')
        ],
        [
            InlineKeyboardButton("⚠️ Warn", callback_data=f'mod_warn_{target_user_id}'),
            InlineKeyboardButton("Kick ❌", callback_data=f'mod_kick_{target_user_id}')
        ],
        [
            InlineKeyboardButton("Unban/Unmute ✅", callback_data=f'mod_unrestrict_{target_user_id}')
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"Moderation Panel for **{target_user_name}**:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def handle_mod_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles button clicks from the inline moderation panel and executes the action."""
    query = update.callback_query
    
    await query.answer()
    
    chat_id = query.message.chat_id
    user_id = query.from_user.id
    
    # 1. Re-check admin permission (SECURITY CHECK)
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        is_admin = isinstance(member, (ChatMemberAdministrator, ChatMemberOwner))

        if not is_admin:
            await query.edit_message_text("🚫 **Permission Denied.** You are not an admin.", parse_mode='Markdown')
            return
            
    except Exception:
        await query.edit_message_text("❌ Error checking admin status.", parse_mode='Markdown')
        return

    # 2. Parse the data: 'mod_ACTION_USERID'
    data_parts = query.data.split('_')
    if len(data_parts) != 3 or data_parts[0] != 'mod':
        await query.edit_message_text("❌ Invalid callback data.", parse_mode='Markdown')
        return
        
    action = data_parts[1]
    target_user_id = int(data_parts[2])
    
    # 3. Execute the Action
    target_user_member = await context.bot.get_chat_member(chat_id, target_user_id)
    target_user_name = target_user_member.user.first_name

    # CHECK 3a: Admin Hierarchy Check
    if await check_target_admin_status(chat_id, target_user_id, context):
        await query.edit_message_text(
            f"🚫 Cannot perform action on **{target_user_name}**: They are an administrator or the group creator.",
            parse_mode='Markdown'
        )
        return
    
    try:
        if action == 'ban':
            await context.bot.ban_chat_member(chat_id, target_user_id)
            new_text = f"✅ Banned **{target_user_name}** permanently."
        
        elif action == 'mute':
            permissions = ChatPermissions()
            await context.bot.restrict_chat_member(chat_id, target_user_id, permissions=permissions)
            
            # Store mute status (Permanent)
            mutes = get_mutes_list(chat_id)
            mutes[target_user_id] = {'expiry': None, 'name': target_user_name} 

            new_text = f"✅ Muted **{target_user_name}** permanently."

        elif action == 'warn':
            # --- REAL WARNING LOGIC (Permanent Mute Enforcement) ---
            chat_data = get_chat_data(chat_id)
            
            current_count = chat_data['warnings'].get(target_user_id, 0)
            if not isinstance(current_count, int): current_count = 0 
            
            new_count = current_count + 1
            warn_limit = chat_data['warn_limit']
            
            if new_count >= warn_limit:
                # EXECUTE PERMANENT MUTE (Final Warning!)
                permissions = ChatPermissions()
                await context.bot.restrict_chat_member(chat_id, target_user_id, permissions=permissions)
                
                mutes = get_mutes_list(chat_id)
                mutes[target_user_id] = {'expiry': None, 'name': target_user_name} 
                
                chat_data['warnings'][target_user_id] = 0
                
                new_text = f"🚨 **Final Warning!** User **{target_user_name}** hit the limit of {warn_limit} warnings and has been **PERMANENTLY MUTED**."
            else:
                # ISSUE WARNING
                chat_data['warnings'][target_user_id] = new_count
                
                new_text = (
                    f"⚠️ Warning issued to **{target_user_name}**.\n"
                    f"**Count:** {new_count} of {warn_limit}"
                )
        
        elif action == 'kick':
            await context.bot.ban_chat_member(chat_id, target_user_id, until_date=int(time.time() + 1))
            await context.bot.unban_chat_member(chat_id, target_user_id)
            new_text = f"❌ Kicked **{target_user_name}**."
            
        elif action == 'unrestrict':
            permissions = ChatPermissions(
                can_send_messages=True, can_send_media_messages=True, can_send_polls=True, 
                can_send_other_messages=True, can_add_web_page_previews=True
            )
            await context.bot.restrict_chat_member(chat_id, target_user_id, permissions=permissions)
            
            mutes = get_mutes_list(chat_id)
            if target_user_id in mutes:
                del mutes[target_user_id]
                
            new_text = f"✅ Unbanned/Unmuted **{target_user_name}**."
            
        else:
            new_text = "❌ Unknown action."

        # 4. Edit the original message to show the action was completed
        await query.edit_message_text(new_text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error executing inline mod action {action}: {e}")
        await query.edit_message_text(f"❌ Failed to execute action. Check bot permissions.", parse_mode='Markdown')

# --- 4. MAIN FUNCTION ---

def main() -> None:
    """Start the bot."""
    application = Application.builder().token(BOT_TOKEN).build()

    # --- STATUS & GREETING HANDLERS ---
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_members))
    greeting_pattern = re.compile(r'^(hello|hi|hey|yo)[\s\S]*$', re.IGNORECASE)
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(greeting_pattern), reply_to_greetings))
    
    # --- COMMAND HANDLERS ---
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("id", id_command))
    application.add_handler(CommandHandler("roll", roll_command)) 
    
    # Quick Mod and Warning Management
    application.add_handler(CommandHandler(["mod", "m"], mod_panel_command)) 
    application.add_handler(CommandHandler("setwarnlimit", set_warn_limit_command))
    application.add_handler(CommandHandler("rwarn", remove_warn_command))      
    application.add_handler(CommandHandler("allwarn", all_warn_command))      
    application.add_handler(CommandHandler("rallwarn", remove_all_warn_command)) 
    
    # Moderation & Locks (Admin Only)
    application.add_handler(CommandHandler("ban", ban_command))
    application.add_handler(CommandHandler("unban", unban_command)) 
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
    
    # --- CALLBACK HANDLERS ---
    application.add_handler(CallbackQueryHandler(handle_mod_callback, pattern='^mod_')) 
    
    # --- MESSAGE HANDLERS (Anti-Spam Logic) ---
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, anti_url_spam_handler))
    
    logger.info("Coco's Manager is starting...")

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
