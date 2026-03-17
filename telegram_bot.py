#!/usr/bin/env python3
import os
import re
import io
import asyncio
from pathlib import Path
from dotenv import load_dotenv
import telebot
from telebot import types
from pymongo import MongoClient
from bson import ObjectId
from PyPDF2 import PdfReader
import fitz  # PyMuPDF
from gtts import gTTS
from emergentintegrations.llm.chat import LlmChat, UserMessage, FileContentWithMimeType
import logging
import tempfile
import time
from PIL import Image
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import numpy as np
import sympy as sp
from sympy import symbols, lambdify, sympify, solve
from sympy.parsing.sympy_parser import parse_expr, standard_transformations, implicit_multiplication_application

# Load environment variables
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Configuration
BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
OWNER_ID = int(os.environ['OWNER_TELEGRAM_ID'])
OWNER_CONTACT = os.environ['OWNER_CONTACT']
EMERGENT_LLM_KEY = os.environ['EMERGENT_LLM_KEY']
MONGO_URL = os.environ['MONGO_URL']
DB_NAME = os.environ['DB_NAME']

# Initialize bot
bot = telebot.TeleBot(BOT_TOKEN)

# MongoDB connection
mongo_client = MongoClient(MONGO_URL)
db = mongo_client[DB_NAME]

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Subjects
SUBJECTS = ['Chemistry', 'Physics', 'Maths', 'Agriculture', 'English', 'IT', 'Biology']

# Store chat sessions (in-memory)
user_sessions = {}

# Helper functions
def get_user(telegram_id):
    return db.users.find_one({"telegram_id": telegram_id})

def create_user(telegram_id, username, first_name):
    user = {
        "telegram_id": telegram_id,
        "username": username,
        "first_name": first_name,
        "status": "pending",
        "language": "en",
        "voice_enabled": False,
        "joined_at": None
    }
    db.users.insert_one(user)
    return user

def detect_language(text):
    amharic_pattern = re.compile('[\u1200-\u137F]')
    if amharic_pattern.search(text):
        return "am"
    return "en"

def remove_markdown_chars(text):
    chars_to_remove = ['*', '_', '`', '~', '|', '$', '@', '#']
    for char in chars_to_remove:
        text = text.replace(char, '')
    return text

def get_or_create_chat_session(telegram_id, language="en"):
    """Get or create chat session with memory"""
    if telegram_id not in user_sessions:
        system_message = f"""You are a friendly, caring, and brilliant 11th-grade teacher and study companion. Think of yourself as the student's best friend who happens to be amazing at teaching!

Your personality:
- 🤗 Warm and friendly (use "Hey!", "Great question!", "Let's figure this out together!")
- 🎓 Expert in all subjects, especially math and science
- 💬 Conversational and encouraging
- 😊 Patient and never judgmental
- 🌟 Enthusiastic about learning

Your teaching approach:

1. **BE A FRIEND FIRST**: Start responses warmly, use conversational language
2. **THINK OUT LOUD**: Show your reasoning process step-by-step
3. **OFFER VISUALS**: When discussing graphs, diagrams, or visual concepts, mention that you can draw them!
   - Say things like: "Would you like me to draw this graph for you?"
   - "I can create a diagram to show this - just ask!"
4. **FOR MATH PROBLEMS**:
   - Solve step-by-step with clear explanations
   - Show WHY each step matters
   - Verify answers
   - Offer alternative methods
5. **FOR SCIENCE**: Use real-world examples, analogies, and offer to draw diagrams
6. **ENCOURAGE**: Celebrate progress, motivate students
7. **REMEMBER**: You have full conversation memory - reference previous discussions
8. **BE AVAILABLE**: Position yourself as always here to help, like a study buddy

When students ask about:
- Graphs/Functions: Mention you can draw them
- Processes: Offer to create flow diagrams
- Structures: Suggest visual representations
- Comparisons: Offer charts or tables

Current language: {language}

You're not just teaching - you're being a supportive friend who makes learning fun and accessible! 🎓✨"""
        
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"telegram_bot_{telegram_id}",
            system_message=system_message
        ).with_model("gemini", "gemini-2.0-flash")
        
        user_sessions[telegram_id] = chat
    
    return user_sessions[telegram_id]

async def get_gemini_response_with_reasoning(user_message, context="", language="en", user_id=None, image_path=None, show_thinking=True):
    """Get response with reasoning process shown"""
    try:
        chat = get_or_create_chat_session(user_id, language)
        
        # Build the prompt with thinking instruction
        if show_thinking:
            thinking_prompt = """First, think through this question step by step:
1. What is being asked?
2. What key concepts are involved?
3. What is the most accurate answer based on knowledge and research?

Then provide your complete answer with reasoning."""
        else:
            thinking_prompt = ""
        
        full_message = user_message
        if context:
            full_message = f"""[Textbook Content]\n{context}\n\n[Student Question]\n{user_message}

{thinking_prompt}

Please explain this clearly and thoroughly as a teacher would, using the textbook content as reference."""
        else:
            full_message = f"""{user_message}

{thinking_prompt}

Provide a thorough, well-researched answer as a knowledgeable teacher would."""
        
        # Handle image if provided
        if image_path:
            # Create file content for image
            file_content = FileContentWithMimeType(
                file_path=image_path,
                mime_type="image/jpeg"
            )
            message = UserMessage(
                text=full_message,
                file_contents=[file_content]
            )
        else:
            message = UserMessage(text=full_message)
        
        response = await chat.send_message(message)
        
        # Remove markdown for Amharic and limit length
        if language == "am":
            response = remove_markdown_chars(response)
        
        # Truncate if too long (Telegram limit is 4096)
        if len(response) > 3500:
            response = response[:3500] + "\n\n... (Ask me to continue for more details)"
        
        return response
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        # Retry once after brief delay
        try:
            await asyncio.sleep(2)
            chat = get_or_create_chat_session(user_id, language)
            message = UserMessage(text=user_message)
            response = await chat.send_message(message)
            if language == "am":
                response = remove_markdown_chars(response)
            if len(response) > 3500:
                response = response[:3500]
            return response
        except Exception as retry_error:
            logger.error(f"Retry failed: {retry_error}")
            return "I apologize, I'm having trouble connecting. Please try again in a moment."

async def get_gemini_response(user_message, context="", language="en", user_id=None):
    """Legacy function for backward compatibility"""
    return await get_gemini_response_with_reasoning(user_message, context, language, user_id, None, False)

def extract_page_text_from_pdf(file_id, page_number):
    try:
        import gridfs
        from pymongo import MongoClient
        
        # Use sync client for GridFS
        sync_client = MongoClient(MONGO_URL)
        sync_db = sync_client[DB_NAME]
        fs = gridfs.GridFS(sync_db)
        
        logger.info(f"Attempting to extract text from page {page_number}, file_id: {file_id}")
        
        pdf_file = fs.get(ObjectId(file_id))
        pdf_content = pdf_file.read()
        
        logger.info(f"PDF file retrieved, size: {len(pdf_content)} bytes")
        
        pdf_reader = PdfReader(io.BytesIO(pdf_content))
        total_pages = len(pdf_reader.pages)
        
        logger.info(f"PDF has {total_pages} pages, requesting page {page_number}")
        
        if page_number < 1 or page_number > total_pages:
            logger.warning(f"Page {page_number} out of range (1-{total_pages})")
            return None
        
        page = pdf_reader.pages[page_number - 1]
        text = page.extract_text()
        
        if text and len(text.strip()) > 0:
            logger.info(f"Successfully extracted {len(text)} characters from page {page_number}")
            return text
        else:
            logger.warning(f"Page {page_number} extracted but no text found")
            return "Page content extracted but no readable text found. The page may contain only images."
            
    except Exception as e:
        logger.error(f"PDF text extraction error for page {page_number}: {e}", exc_info=True)
        return None

def extract_page_image_from_pdf(file_id, page_number):
    """Extract page as image from PDF"""
    try:
        import gridfs
        from pymongo import MongoClient
        
        # Use sync client for GridFS
        sync_client = MongoClient(MONGO_URL)
        sync_db = sync_client[DB_NAME]
        fs = gridfs.GridFS(sync_db)
        
        logger.info(f"Attempting to extract image from page {page_number}, file_id: {file_id}")
        
        pdf_file = fs.get(ObjectId(file_id))
        pdf_content = pdf_file.read()
        
        logger.info(f"PDF file retrieved for image extraction, size: {len(pdf_content)} bytes")
        
        # Use PyMuPDF to convert page to image
        doc = fitz.open(stream=pdf_content, filetype="pdf")
        total_pages = len(doc)
        
        logger.info(f"PDF opened with {total_pages} pages, requesting page {page_number}")
        
        if page_number < 1 or page_number > total_pages:
            logger.warning(f"Page {page_number} out of range for image (1-{total_pages})")
            doc.close()
            return None
        
        page = doc[page_number - 1]
        
        # Render page to image with good quality
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom for better quality
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_file:
            pix.save(temp_file.name)
            logger.info(f"Page {page_number} saved as image: {temp_file.name}")
            doc.close()
            return temp_file.name
            
    except Exception as e:
        logger.error(f"PDF image extraction error for page {page_number}: {e}", exc_info=True)
        return None

def create_text_to_speech(text, language="en"):
    try:
        lang_map = {"en": "en", "am": "am"}
        lang_code = lang_map.get(language, "en")
        
        # Limit text length for TTS
        if len(text) > 1000:
            text = text[:1000] + "..."
        
        tts = gTTS(text=text, lang=lang_code, slow=False)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_file:
            tts.save(temp_file.name)
            return temp_file.name
    except Exception as e:
        logger.error(f"TTS error: {e}")
        return None

def parse_mathematical_expression(text):
    """Extract and parse mathematical expressions from text"""
    try:
        # Look for common patterns
        patterns = [
            r'[yf]\s*=\s*([^,\.\n]+)',  # y = expression or f(x) = expression
            r'plot\s+([^,\.\n]+)',      # plot expression
            r'graph\s+([^,\.\n]+)',     # graph expression
            r'draw\s+([^,\.\n]+)',      # draw expression
            r'equation[:\s]+([^,\.\n]+)', # equation: expression
        ]
        
        expression = None
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                expression = match.group(1).strip()
                break
        
        # If no pattern found, try to find standalone mathematical expression
        if not expression:
            # Look for expressions with x, numbers, and operators
            math_pattern = r'[x\d\+\-\*/\^\(\)\s]+'
            matches = re.findall(math_pattern, text)
            if matches:
                # Find the longest match that looks like an equation
                expression = max(matches, key=len).strip()
        
        if expression:
            # Clean up the expression
            expression = expression.replace('^', '**')  # Convert ^ to **
            expression = expression.replace('×', '*')   # Convert × to *
            expression = expression.replace('÷', '/')   # Convert ÷ to /
            
            # Try to parse it with sympy
            x = symbols('x')
            transformations = standard_transformations + (implicit_multiplication_application,)
            try:
                expr = parse_expr(expression, transformations=transformations)
                return expr, expression
            except:
                # Try sympify as fallback
                expr = sympify(expression)
                return expr, expression
                
        return None, None
        
    except Exception as e:
        logger.error(f"Math expression parsing error: {e}")
        return None, None

def generate_smart_graph(user_question, expression_str=None):
    """Generate accurate mathematical graph based on user's equation"""
    try:
        # First, try to parse expression from question
        expr, expr_text = parse_mathematical_expression(user_question)
        
        if expr is None and expression_str:
            # Try provided expression
            expr, expr_text = parse_mathematical_expression(expression_str)
        
        if expr is None:
            # Fallback to keyword-based generation
            return generate_graph_image("auto", user_question, "Mathematical Function")
        
        # Create the plot
        fig, ax = plt.subplots(figsize=(10, 7))
        
        x = symbols('x')
        
        # Convert sympy expression to numpy function
        f = lambdify(x, expr, modules=['numpy'])
        
        # Determine appropriate x range based on expression
        # Try to find roots or critical points
        try:
            # Find approximate range
            test_points = [-10, -5, -1, 0, 1, 5, 10]
            test_values = []
            for point in test_points:
                try:
                    val = float(f(point))
                    if not np.isnan(val) and not np.isinf(val):
                        test_values.append(abs(val))
                except:
                    pass
            
            if test_values:
                max_val = max(test_values)
                if max_val > 100:
                    x_range = (-10, 10)
                elif max_val > 10:
                    x_range = (-5, 5)
                else:
                    x_range = (-10, 10)
            else:
                x_range = (-10, 10)
        except:
            x_range = (-10, 10)
        
        # Generate points
        x_vals = np.linspace(x_range[0], x_range[1], 1000)
        
        try:
            y_vals = f(x_vals)
            
            # Filter out inf and nan values
            mask = np.isfinite(y_vals)
            x_vals = x_vals[mask]
            y_vals = y_vals[mask]
            
            if len(x_vals) > 0:
                # Plot the function
                ax.plot(x_vals, y_vals, 'b-', linewidth=2.5, label=f'y = {expr_text}')
                
                # Add grid
                ax.grid(True, alpha=0.3, linestyle='--')
                
                # Add axes
                ax.axhline(y=0, color='k', linewidth=0.8)
                ax.axvline(x=0, color='k', linewidth=0.8)
                
                # Find and mark critical points
                try:
                    # Find roots (where y = 0)
                    roots = solve(expr, x)
                    real_roots = [float(r.evalf()) for r in roots if r.is_real and x_range[0] <= float(r.evalf()) <= x_range[1]]
                    
                    if real_roots:
                        root_y = [0] * len(real_roots)
                        ax.plot(real_roots, root_y, 'ro', markersize=8, label='Roots', zorder=5)
                        
                        # Annotate roots
                        for root in real_roots[:3]:  # Show max 3 roots
                            ax.annotate(f'x = {root:.2f}',
                                      xy=(root, 0),
                                      xytext=(root, -max(abs(y_vals))*0.1),
                                      fontsize=9,
                                      ha='center',
                                      bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.7))
                except Exception as e:
                    logger.debug(f"Could not find roots: {e}")
                
                # Set labels
                ax.set_xlabel('x', fontsize=13, fontweight='bold')
                ax.set_ylabel('y', fontsize=13, fontweight='bold')
                ax.set_title(f'Graph: y = {expr_text}', fontsize=15, fontweight='bold', pad=15)
                
                # Add legend
                ax.legend(fontsize=11, loc='best')
                
                # Set reasonable y limits
                y_range = np.ptp(y_vals)
                y_center = np.mean(y_vals)
                if y_range > 0:
                    ax.set_ylim(y_center - y_range, y_center + y_range)
                
                # Add equation box
                eq_text = f'Equation: y = {expr_text}'
                ax.text(0.02, 0.98, eq_text,
                       transform=ax.transAxes,
                       fontsize=10,
                       verticalalignment='top',
                       bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
                
        except Exception as e:
            logger.error(f"Error plotting function: {e}")
            ax.text(0.5, 0.5, f'Could not plot: {expr_text}\nError: {str(e)}',
                   ha='center', va='center', fontsize=12, color='red')
        
        # Save to file
        plt.tight_layout()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_file:
            plt.savefig(temp_file.name, dpi=150, bbox_inches='tight', facecolor='white')
            plt.close()
            return temp_file.name
            
    except Exception as e:
        logger.error(f"Smart graph generation error: {e}")
        plt.close()
        return None

def analyze_math_question_and_generate(user_question, telegram_id, language):
    """Analyze the question, understand what's needed, then generate appropriate visualization"""
    try:
        bot.send_message(telegram_id, "🔍 Let me understand what you're asking...")
        
        # First, let AI understand the question
        async def understand_question():
            understanding_prompt = f"""Analyze this student's question: "{user_question}"

Please identify:
1. Is this asking for a graph or visualization?
2. If yes, what mathematical expression or equation should be graphed?
3. Extract the exact equation/expression (e.g., "2x + 3", "x^2 - 4x + 3")

Respond in this format:
NEEDS_GRAPH: yes/no
EQUATION: [the mathematical expression]
EXPLANATION: [brief explanation of what should be shown]"""
            
            chat = get_or_create_chat_session(telegram_id, language)
            message = UserMessage(text=understanding_prompt)
            return await chat.send_message(message)
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        analysis = loop.run_until_complete(understand_question())
        loop.close()
        
        logger.info(f"AI Analysis: {analysis}")
        
        # Check if graph is needed
        needs_graph = "yes" in analysis.lower() and ("graph" in analysis.lower() or "equation" in analysis.lower())
        
        if needs_graph:
            # Extract equation
            equation_match = re.search(r'EQUATION:\s*(.+?)(?:\n|$)', analysis, re.IGNORECASE)
            if equation_match:
                equation = equation_match.group(1).strip()
                bot.send_message(telegram_id, f"📊 Creating graph for: {equation}")
                
                # Generate smart graph
                graph_path = generate_smart_graph(user_question, equation)
                
                return graph_path, analysis
        
        return None, analysis
        
    except Exception as e:
        logger.error(f"Question analysis error: {e}")
        return None, None

def check_if_needs_visual(text):
    """Check if the question needs a visual diagram/graph"""
    visual_keywords = [
        'draw', 'graph', 'plot', 'diagram', 'chart', 'illustrate', 'show me',
        'visualize', 'sketch', 'picture', 'sine', 'cosine', 'parabola', 
        'circle', 'triangle', 'square', 'function', 'curve', 'line'
    ]
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in visual_keywords)

def create_subject_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    buttons = [types.InlineKeyboardButton(subject, callback_data=f"subject_{subject}") for subject in SUBJECTS]
    keyboard.add(*buttons)
    return keyboard

def create_feature_keyboard():
    """Create keyboard for additional features"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("💬 AI Chat", callback_data="feature_chat"),
        types.InlineKeyboardButton("📚 Subjects", callback_data="show_subjects")
    )
    keyboard.add(
        types.InlineKeyboardButton("📝 Homework", callback_data="feature_homework"),
        types.InlineKeyboardButton("📋 Assignment", callback_data="feature_assignment")
    )
    keyboard.add(
        types.InlineKeyboardButton("📖 Story", callback_data="feature_story"),
        types.InlineKeyboardButton("📸 Analyze Image", callback_data="feature_image")
    )
    keyboard.add(
        types.InlineKeyboardButton("⚙️ Settings", callback_data="show_settings")
    )
    return keyboard

def create_settings_keyboard(voice_enabled):
    keyboard = types.InlineKeyboardMarkup()
    voice_text = "🔊 Voice: ON" if voice_enabled else "🔇 Voice: OFF"
    keyboard.add(types.InlineKeyboardButton(voice_text, callback_data="toggle_voice"))
    keyboard.add(types.InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_menu"))
    return keyboard

# Bot handlers
@bot.message_handler(commands=['start'])
def handle_start(message):
    telegram_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    user = get_user(telegram_id)
    
    if not user:
        create_user(telegram_id, username, first_name)
        
        if telegram_id != OWNER_ID:
            try:
                owner_message = f"""🆕 New User Request

User: {first_name}
Username: @{username if username else 'N/A'}
Telegram ID: {telegram_id}

Approve or reject this user?"""
                
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(
                    types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_{telegram_id}"),
                    types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_{telegram_id}")
                )
                keyboard.add(types.InlineKeyboardButton("🚫 Ban", callback_data=f"ban_{telegram_id}"))
                
                bot.send_message(OWNER_ID, owner_message, reply_markup=keyboard)
            except Exception as e:
                logger.error(f"Failed to notify owner: {e}")
        
        if telegram_id == OWNER_ID:
            db.users.update_one({"telegram_id": telegram_id}, {"$set": {"status": "approved"}})
            welcome_message = """👑 Welcome Bot King!

You have full access. Use the menu below:"""
            bot.reply_to(message, welcome_message, reply_markup=create_feature_keyboard())
        else:
            wait_message = f"""⏳ Wait For bot king accept K.K✅

Your request has been sent to the admin.
You will be notified once approved.

Contact owner: {OWNER_CONTACT}"""
            bot.reply_to(message, wait_message)
    else:
        if user['status'] == 'pending':
            bot.reply_to(message, f"⏳ Your request is still pending. Please wait for approval.\nContact: {OWNER_CONTACT}")
        elif user['status'] == 'approved':
            welcome_message = f"""🎓 Hey {first_name}! Welcome back, my friend! 👋

I'm so happy to see you! I'm your AI study buddy and teacher, here to help you learn and succeed! 🌟

What I can do for you:

📚 **Explain ANY concept** - Just ask me!
📄 **Analyze textbook pages** - Send me page numbers
📝 **Create homework** - Practice questions
📋 **Generate assignments** - Structured tasks
📖 **Tell stories** - Make learning fun
📸 **Analyze images** - Upload any educational image
💬 **Chat freely** - Ask me ANYTHING
📊 **Draw graphs & diagrams** - I can visualize concepts!
🗣️ **Voice explanations** - In English or Amharic

I'm not just a bot - I'm your friend who loves helping you learn! Let's explore knowledge together! 😊

Use the menu below or just start chatting! 💫"""
            bot.reply_to(message, welcome_message, reply_markup=create_feature_keyboard())
        elif user['status'] == 'rejected':
            bot.reply_to(message, f"❌ Your access was rejected. Contact: {OWNER_CONTACT}")
        elif user['status'] == 'banned':
            bot.reply_to(message, f"🚫 You are banned from using this bot. Contact: {OWNER_CONTACT}")

@bot.message_handler(commands=['menu'])
def handle_menu(message):
    telegram_id = message.from_user.id
    user = get_user(telegram_id)
    
    if not user or user['status'] != 'approved':
        bot.reply_to(message, "❌ You need to be approved to use this command.")
        return
    
    bot.reply_to(message, "📱 Main Menu:", reply_markup=create_feature_keyboard())

@bot.callback_query_handler(func=lambda call: call.data == 'back_to_menu')
def handle_back_to_menu(call):
    bot.edit_message_text(
        "📱 Main Menu:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=create_feature_keyboard()
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == 'show_subjects')
def handle_show_subjects(call):
    bot.edit_message_text(
        "📚 Select a subject:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=create_subject_keyboard()
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == 'show_settings')
def handle_show_settings(call):
    telegram_id = call.from_user.id
    user = get_user(telegram_id)
    voice_enabled = user.get('voice_enabled', False)
    
    bot.edit_message_text(
        f"""⚙️ Settings

Voice Responses: {'Enabled' if voice_enabled else 'Disabled'}
Language: Auto-detect (English/Amharic)

Toggle voice responses below:""",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=create_settings_keyboard(voice_enabled)
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('subject_'))
def handle_subject_selection(call):
    telegram_id = call.from_user.id
    user = get_user(telegram_id)
    
    if not user or user['status'] != 'approved':
        bot.answer_callback_query(call.id, "❌ Not approved")
        return
    
    subject = call.data.replace('subject_', '')
    
    db.users.update_one(
        {"telegram_id": telegram_id},
        {"$set": {"current_subject": subject}}
    )
    
    bot.answer_callback_query(call.id, f"✅ {subject} selected")
    bot.edit_message_text(
        f"""📚 {subject} selected!

You can now:
• Ask questions about {subject}
• Request page explanations: "{subject} page 15"
• Generate homework questions
• Create assignments
• Ask for educational stories

What would you like to learn today?""",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=create_feature_keyboard()
    )

@bot.callback_query_handler(func=lambda call: call.data == 'feature_homework')
def handle_homework_request(call):
    telegram_id = call.from_user.id
    user = get_user(telegram_id)
    
    if not user or user['status'] != 'approved':
        bot.answer_callback_query(call.id, "❌ Not approved")
        return
    
    current_subject = user.get('current_subject', 'general')
    bot.answer_callback_query(call.id)
    
    bot.send_message(
        telegram_id,
        f"""📝 Generating homework questions for {current_subject}...

Please specify the topic you want homework on, or I'll create general practice questions.

Example: "Homework on chemical reactions"""
    )
    
    # Store state
    db.users.update_one(
        {"telegram_id": telegram_id},
        {"$set": {"waiting_for": "homework_topic"}}
    )

@bot.callback_query_handler(func=lambda call: call.data == 'feature_assignment')
def handle_assignment_request(call):
    telegram_id = call.from_user.id
    user = get_user(telegram_id)
    
    if not user or user['status'] != 'approved':
        bot.answer_callback_query(call.id, "❌ Not approved")
        return
    
    current_subject = user.get('current_subject', 'general')
    bot.answer_callback_query(call.id)
    
    bot.send_message(
        telegram_id,
        f"""📋 Creating assignment for {current_subject}...

Please specify the topic, or I'll create a comprehensive assignment.

Example: "Assignment on Newton's laws"""
    )
    
    db.users.update_one(
        {"telegram_id": telegram_id},
        {"$set": {"waiting_for": "assignment_topic"}}
    )

@bot.callback_query_handler(func=lambda call: call.data == 'feature_story')
def handle_story_request(call):
    telegram_id = call.from_user.id
    user = get_user(telegram_id)
    
    if not user or user['status'] != 'approved':
        bot.answer_callback_query(call.id, "❌ Not approved")
        return
    
    current_subject = user.get('current_subject', 'general')
    bot.answer_callback_query(call.id)
    
    bot.send_message(
        telegram_id,
        f"""📖 Creating educational story for {current_subject}...

Please tell me the topic, or I'll create an interesting story.

Example: "Story about photosynthesis"""
    )
    
    db.users.update_one(
        {"telegram_id": telegram_id},
        {"$set": {"waiting_for": "story_topic"}}
    )

@bot.callback_query_handler(func=lambda call: call.data == 'feature_chat')
def handle_chat_request(call):
    telegram_id = call.from_user.id
    user = get_user(telegram_id)
    
    if not user or user['status'] != 'approved':
        bot.answer_callback_query(call.id, "❌ Not approved")
        return
    
    bot.answer_callback_query(call.id, "💬 AI Chat Mode activated!")
    
    bot.send_message(
        telegram_id,
        """💬 AI Chat Mode - Your Friendly Teacher!

Hi friend! 👋 I'm here to help you learn anything!

Ask me ANYTHING and I'll:
✅ Think deeply about your question
✅ Explain with reasoning and examples
✅ Draw graphs/diagrams when needed
✅ Remember our conversation
✅ Be your friendly study companion

Examples:
• "What is photosynthesis?"
• "Solve 3x² - 5x + 2 = 0"
• "Draw a sine wave graph"
• "Explain gravity to me"
• "Help me understand cells"

I can even create visual aids like:
📊 Graphs and charts
📐 Diagrams and illustrations
📈 Mathematical plots
🎨 Concept visualizations

Just ask your question! I'm here for you! 😊"""
    )
    
    db.users.update_one(
        {"telegram_id": telegram_id},
        {"$set": {"chat_mode": True}}
    )

@bot.callback_query_handler(func=lambda call: call.data == 'feature_image')
def handle_image_request(call):
    telegram_id = call.from_user.id
    user = get_user(telegram_id)
    
    if not user or user['status'] != 'approved':
        bot.answer_callback_query(call.id, "❌ Not approved")
        return
    
    bot.answer_callback_query(call.id)
    
    bot.send_message(
        telegram_id,
        """📸 Image Analysis Mode

Send me any image and ask a question about it!

Examples:
• Send a diagram → "Explain this diagram"
• Send a math problem → "Solve this problem"
• Send a graph → "What does this graph show?"
• Send a biology image → "Identify this organism"
• Send handwritten notes → "What does this say?"

Just send the image now, and I'll analyze it with reasoning! 🧠"""
    )
    
    db.users.update_one(
        {"telegram_id": telegram_id},
        {"$set": {"waiting_for": "image_analysis"}}
    )

@bot.callback_query_handler(func=lambda call: call.data == 'toggle_voice')
def handle_toggle_voice(call):
    telegram_id = call.from_user.id
    user = get_user(telegram_id)
    
    if not user:
        return
    
    current_voice = user.get('voice_enabled', False)
    new_voice = not current_voice
    
    db.users.update_one(
        {"telegram_id": telegram_id},
        {"$set": {"voice_enabled": new_voice}}
    )
    
    status = "enabled" if new_voice else "disabled"
    bot.answer_callback_query(call.id, f"🔊 Voice {status}")
    
    bot.edit_message_reply_markup(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=create_settings_keyboard(new_voice)
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('approve_'))
def handle_approve_user(call):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "❌ Only owner can approve")
        return
    
    telegram_id = int(call.data.replace('approve_', ''))
    
    db.users.update_one(
        {"telegram_id": telegram_id},
        {"$set": {"status": "approved"}}
    )
    
    bot.answer_callback_query(call.id, "✅ User approved")
    bot.edit_message_text(
        f"{call.message.text}\n\n✅ APPROVED",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id
    )
    
    try:
        bot.send_message(
            telegram_id,
            """🎉 Congratulations!

Your access has been approved by the bot king!

You can now use all features. Type /start to begin."""
        )
    except Exception as e:
        logger.error(f"Failed to notify user: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('reject_'))
def handle_reject_user(call):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "❌ Only owner can reject")
        return
    
    telegram_id = int(call.data.replace('reject_', ''))
    
    db.users.update_one(
        {"telegram_id": telegram_id},
        {"$set": {"status": "rejected"}}
    )
    
    bot.answer_callback_query(call.id, "❌ User rejected")
    bot.edit_message_text(
        f"{call.message.text}\n\n❌ REJECTED",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id
    )
    
    try:
        bot.send_message(
            telegram_id,
            f"""❌ Access Rejected

Your request has been rejected.
Contact: {OWNER_CONTACT} for more information."""
        )
    except Exception as e:
        logger.error(f"Failed to notify user: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('ban_'))
def handle_ban_user(call):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "❌ Only owner can ban")
        return
    
    telegram_id = int(call.data.replace('ban_', ''))
    
    db.users.update_one(
        {"telegram_id": telegram_id},
        {"$set": {"status": "banned"}}
    )
    
    bot.answer_callback_query(call.id, "🚫 User banned")
    bot.edit_message_text(
        f"{call.message.text}\n\n🚫 BANNED",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id
    )
    
    try:
        bot.send_message(
            telegram_id,
            f"""🚫 Banned

You have been banned from using this bot.
Contact: {OWNER_CONTACT}"""
        )
    except Exception as e:
        logger.error(f"Failed to notify user: {e}")

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    telegram_id = message.from_user.id
    user = get_user(telegram_id)
    
    if not user or user['status'] != 'approved':
        bot.reply_to(message, "❌ You need to be approved first. Type /start to register.")
        return
    
    # Check if user is in image analysis mode
    waiting_for = user.get('waiting_for')
    
    if waiting_for == 'image_analysis':
        process_image_analysis(message)
    else:
        bot.reply_to(message, "📸 To analyze images, use the 'Analyze Image' feature from the menu first!")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    telegram_id = message.from_user.id
    user = get_user(telegram_id)
    
    if not user or user['status'] != 'approved':
        bot.reply_to(message, "❌ You need to be approved first. Type /start to register.")
        return
    
    user_text = message.text
    language = detect_language(user_text)
    
    db.users.update_one(
        {"telegram_id": telegram_id},
        {"$set": {"language": language}}
    )
    
    # Check if user is in a special mode
    waiting_for = user.get('waiting_for')
    
    if waiting_for == 'homework_topic':
        db.users.update_one({"telegram_id": telegram_id}, {"$unset": {"waiting_for": ""}})
        process_homework_generation(message, user_text, language)
        return
    elif waiting_for == 'assignment_topic':
        db.users.update_one({"telegram_id": telegram_id}, {"$unset": {"waiting_for": ""}})
        process_assignment_generation(message, user_text, language)
        return
    elif waiting_for == 'story_topic':
        db.users.update_one({"telegram_id": telegram_id}, {"$unset": {"waiting_for": ""}})
        process_story_generation(message, user_text, language)
        return
    elif waiting_for == 'image_analysis':
        # User sent text while in image analysis mode
        bot.reply_to(message, "📸 Please send an image for analysis, or use /menu to return to the main menu.")
        return
    
    # Check for page-specific query
    page_pattern = re.compile(r'page\s+(\d+)', re.IGNORECASE)
    page_match = page_pattern.search(user_text)
    
    # Check for subject mention
    subject_mentioned = None
    for subject in SUBJECTS:
        if subject.lower() in user_text.lower():
            subject_mentioned = subject
            break
    
    current_subject = user.get('current_subject', subject_mentioned)
    
    if page_match:
        page_number = int(page_match.group(1))
        process_page_query(message, current_subject, page_number, user_text, language)
    else:
        process_general_query(message, user_text, language)

def process_page_query(message, subject, page_number, user_text, language):
    telegram_id = message.from_user.id
    
    if not subject:
        bot.reply_to(message, "Please select a subject first using /menu → Subjects")
        return
    
    textbook = db.textbooks.find_one({"subject": subject})
    
    if not textbook:
        bot.reply_to(message, f"📚 No textbook found for {subject}. Please upload one in the dashboard.")
        return
    
    total_pages = textbook.get('total_pages', 0)
    
    # Validate page number
    if page_number > total_pages:
        bot.reply_to(message, 
            f"❌ Page {page_number} does not exist.\n\n"
            f"📚 {subject} textbook has only {total_pages} pages.\n"
            f"Please choose a page between 1 and {total_pages}.")
        return
    
    bot.send_message(telegram_id, f"📄 Extracting {subject} page {page_number} of {total_pages}...")
    
    # Extract page image first
    page_image_path = extract_page_image_from_pdf(textbook['file_id'], page_number)
    
    if page_image_path:
        try:
            with open(page_image_path, 'rb') as photo:
                bot.send_photo(telegram_id, photo, caption=f"📄 {subject} - Page {page_number}/{total_pages}")
        except Exception as e:
            logger.error(f"Failed to send page image: {e}")
            bot.send_message(telegram_id, "⚠️ Could not send page image, but will still analyze the text content.")
    else:
        logger.warning(f"Could not extract image for page {page_number}")
        bot.send_message(telegram_id, "⚠️ Could not extract page image, but will try to analyze text content...")
    
    # Extract page text
    page_content = extract_page_text_from_pdf(textbook['file_id'], page_number)
    
    if not page_content:
        error_msg = f"❌ Could not extract text from page {page_number}.\n\n"
        error_msg += f"This could mean:\n"
        error_msg += f"• The page may contain only images/diagrams\n"
        error_msg += f"• The PDF may be scanned (not text-based)\n"
        error_msg += f"• There was a technical error\n\n"
        
        if page_image_path and os.path.exists(page_image_path):
            error_msg += f"✅ I sent you the page screenshot above.\n"
            error_msg += f"You can also try uploading the screenshot to me using 'Analyze Image' feature!"
            os.unlink(page_image_path)
        
        bot.reply_to(message, error_msg)
        return
    
    bot.send_chat_action(telegram_id, 'typing')
    bot.send_message(telegram_id, "🧠 Analyzing page with deep reasoning...")
    
    # Get AI explanation with IMAGE + TEXT + REASONING
    async def get_response():
        # Enhanced prompt for math and science
        if subject.lower() in ['maths', 'math', 'physics', 'chemistry']:
            prompt = f"""I need you to analyze page {page_number} from {subject} textbook.

IMPORTANT INSTRUCTIONS:
1. Look at the page image carefully - see all equations, diagrams, graphs, and formulas
2. Read the text content provided
3. Think step-by-step about the concepts
4. For math problems: Show complete solutions with reasoning for each step
5. For science: Explain concepts thoroughly with examples
6. Use the actual content from the page

Please analyze and explain everything on this page as a knowledgeable teacher would."""
        else:
            prompt = f"""Analyze page {page_number} from {subject} textbook.

Look at the page image and read the text carefully.
Explain all concepts clearly with reasoning and examples.
Be thorough like a real teacher."""
        
        # Use reasoning mode with IMAGE for best results
        return await get_gemini_response_with_reasoning(
            prompt, 
            page_content, 
            language, 
            telegram_id,
            image_path=page_image_path if page_image_path and os.path.exists(page_image_path) else None,
            show_thinking=True
        )
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        response = loop.run_until_complete(get_response())
        loop.close()
        
        # Clean up temp image file
        if page_image_path and os.path.exists(page_image_path):
            os.unlink(page_image_path)
        
        bot.send_message(telegram_id, f"📖 Analysis:\n\n{response}")
        
        # Save conversation
        save_conversation(telegram_id, user_text, response, subject, page_number)
        
        # Send voice if enabled
        send_voice_if_enabled(telegram_id, response, language)
        
    except Exception as e:
        logger.error(f"Error in page analysis: {e}", exc_info=True)
        if page_image_path and os.path.exists(page_image_path):
            os.unlink(page_image_path)
        bot.send_message(telegram_id, 
            f"❌ Sorry, I encountered an error analyzing page {page_number}.\n"
            f"Please try again or contact support if the issue persists.")

def process_general_query(message, user_text, language):
    telegram_id = message.from_user.id
    
    # Check if this might need a mathematical visualization
    needs_visual = check_if_needs_visual(user_text)
    
    if needs_visual:
        # Use intelligent analysis
        graph_path, analysis = analyze_math_question_and_generate(user_text, telegram_id, language)
        
        if graph_path and os.path.exists(graph_path):
            # Send the graph
            try:
                with open(graph_path, 'rb') as photo:
                    bot.send_photo(telegram_id, photo, 
                                  caption="📊 Here's the accurate graph for your equation!")
                os.unlink(graph_path)
            except Exception as e:
                logger.error(f"Failed to send graph: {e}")
        
        # Now get detailed explanation
        bot.send_chat_action(telegram_id, 'typing')
        bot.send_message(telegram_id, "🧠 Now let me explain this in detail...")
    else:
        bot.send_chat_action(telegram_id, 'typing')
        bot.send_message(telegram_id, "🧠 Let me think about this...")
    
    # Get AI response with reasoning
    async def get_response():
        return await get_gemini_response_with_reasoning(
            user_text, 
            "", 
            language, 
            telegram_id,
            image_path=None,
            show_thinking=True
        )
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    response = loop.run_until_complete(get_response())
    loop.close()
    
    bot.send_message(telegram_id, response)
    
    save_conversation(telegram_id, user_text, response, None, None)
    send_voice_if_enabled(telegram_id, response, language)

def process_homework_generation(message, topic, language):
    telegram_id = message.from_user.id
    user = get_user(telegram_id)
    current_subject = user.get('current_subject', 'general')
    
    bot.send_chat_action(telegram_id, 'typing')
    
    async def get_response():
        prompt = f"""Generate 8-10 homework practice questions for 11th-grade students on the topic: {topic}
        
Subject: {current_subject}
        
Make questions:
1. Clear and specific
2. Progressive difficulty (easy to challenging)
3. Cover different aspects of the topic
4. Include variety (multiple choice, short answer, problems)
5. Educational and thought-provoking
        
Format each question clearly with numbers."""
        return await get_gemini_response(prompt, "", language, telegram_id)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    response = loop.run_until_complete(get_response())
    loop.close()
    
    bot.send_message(telegram_id, f"📝 Homework Questions:\n\n{response}")
    save_conversation(telegram_id, f"Homework: {topic}", response, current_subject, None)
    send_voice_if_enabled(telegram_id, response, language)

def process_assignment_generation(message, topic, language):
    telegram_id = message.from_user.id
    user = get_user(telegram_id)
    current_subject = user.get('current_subject', 'general')
    
    bot.send_chat_action(telegram_id, 'typing')
    
    async def get_response():
        prompt = f"""Create a comprehensive assignment for 11th-grade students on: {topic}
        
Subject: {current_subject}
        
Include:
1. Clear objectives (what students will learn)
2. Instructions for completing the assignment
3. 3-5 main tasks/questions
4. Optional research component
5. Grading criteria
        
Make it structured and educational."""
        return await get_gemini_response(prompt, "", language, telegram_id)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    response = loop.run_until_complete(get_response())
    loop.close()
    
    bot.send_message(telegram_id, f"📋 Assignment:\n\n{response}")
    save_conversation(telegram_id, f"Assignment: {topic}", response, current_subject, None)
    send_voice_if_enabled(telegram_id, response, language)

def process_story_generation(message, topic, language):
    telegram_id = message.from_user.id
    user = get_user(telegram_id)
    current_subject = user.get('current_subject', 'general')
    
    bot.send_chat_action(telegram_id, 'typing')
    
    async def get_response():
        prompt = f"""Create an engaging educational story for 11th-grade students about: {topic}
        
Subject: {current_subject}
        
Make the story:
1. Entertaining and relatable
2. Scientifically/historically accurate
3. Include characters and a plot
4. Teach key concepts naturally through the narrative
5. Have a clear educational message
        
Keep it concise but engaging (max 2500 characters)."""
        return await get_gemini_response(prompt, "", language, telegram_id)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    response = loop.run_until_complete(get_response())
    loop.close()
    
    bot.send_message(telegram_id, f"📖 Story:\n\n{response}")
    save_conversation(telegram_id, f"Story: {topic}", response, current_subject, None)
    send_voice_if_enabled(telegram_id, response, language)

def process_image_analysis(message):
    telegram_id = message.from_user.id
    user = get_user(telegram_id)
    language = user.get('language', 'en')
    
    # Clear the waiting state
    db.users.update_one({"telegram_id": telegram_id}, {"$unset": {"waiting_for": ""}})
    
    bot.send_chat_action(telegram_id, 'typing')
    bot.send_message(telegram_id, "🔍 Analyzing your image with AI reasoning...")
    
    try:
        # Get the largest photo size
        photo = message.photo[-1]
        file_info = bot.get_file(photo.file_id)
        
        # Download the image
        downloaded_file = bot.download_file(file_info.file_path)
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_file:
            temp_file.write(downloaded_file)
            image_path = temp_file.name
        
        # Get user's question from caption or use default
        user_question = message.caption if message.caption else "Analyze this image and explain what you see with detailed reasoning."
        
        async def get_response():
            return await get_gemini_response_with_reasoning(
                user_question, 
                "", 
                language, 
                telegram_id, 
                image_path, 
                show_thinking=True
            )
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        response = loop.run_until_complete(get_response())
        loop.close()
        
        # Clean up temp file
        os.unlink(image_path)
        
        bot.send_message(telegram_id, f"🧠 Image Analysis:\n\n{response}")
        save_conversation(telegram_id, f"Image Analysis: {user_question}", response, None, None)
        send_voice_if_enabled(telegram_id, response, language)
        
    except Exception as e:
        logger.error(f"Image analysis error: {e}")
        bot.send_message(telegram_id, "❌ Sorry, I couldn't analyze the image. Please try again.")

def save_conversation(telegram_id, message, response, subject, page_number):
    conversation = {
        "telegram_id": telegram_id,
        "message": message,
        "response": response,
        "subject": subject,
        "page_number": page_number,
        "timestamp": None
    }
    db.conversations.insert_one(conversation)

def send_voice_if_enabled(telegram_id, text, language):
    user = get_user(telegram_id)
    if user.get('voice_enabled', False):
        bot.send_chat_action(telegram_id, 'record_audio')
        voice_file = create_text_to_speech(text, language)
        
        if voice_file:
            try:
                with open(voice_file, 'rb') as audio:
                    bot.send_voice(telegram_id, audio)
                os.unlink(voice_file)
            except Exception as e:
                logger.error(f"Failed to send voice: {e}")

if __name__ == "__main__":
    logger.info("🤖 Telegram bot starting...")
    logger.info(f"Owner ID: {OWNER_ID}")
    
    # Improved reliability with auto-reconnect
    while True:
        try:
            logger.info("✅ Bot is now running and ready to receive messages!")
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            logger.error(f"⚠️ Bot disconnected: {e}")
            logger.info("🔄 Attempting to reconnect in 5 seconds...")
            time.sleep(5)
            logger.info("🔄 Reconnecting...")