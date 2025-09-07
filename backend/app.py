import os
import datetime
import uuid
import json
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv
import google.generativeai as genai
import pdfplumber
import firebase_admin
from firebase_admin import credentials, auth, firestore

# --- INITIALIZATION ---
load_dotenv()
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
app = Flask(__name__, static_folder='../frontend', static_url_path='/')

# --- HELPER FUNCTIONS ---
def extract_text_from_pdf(file_stream):
    text = ""
    try:
        with pdfplumber.open(file_stream) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text
    except Exception as e:
        print(f"Error reading PDF with pdfplumber: {e}")
        return None

def get_gemini_response(prompt):
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    try:
        response = model.generate_content(prompt)
        # Clean up potential markdown formatting
        cleaned_text = response.text.strip().replace('```json', '').replace('```', '').strip()
        return cleaned_text
    except Exception as e:
        print(f"Gemini API Error: {e}")
        return f"Sorry, there was an error with the AI model: {e}"

# --- NEW & UPDATED PROMPT TEMPLATES ---

# 1. Main Analysis Prompt (Now asks for JSON output)
MAIN_ANALYSIS_PROMPT = """
Analyze the following legal document from India. Provide a multi-part response in the {language} language.

**Part 1: Key Information JSON**
Extract the most critical data points into a valid JSON object. The keys should be in English. For any value not found, use "Not specified".
- For a Rental Agreement: {{ "parties": "...", "property_address": "...", "rent_amount": "...", "security_deposit": "...", "lease_duration": "..." }}
- For a Loan Contract: {{ "parties": "...", "loan_amount": "...", "interest_rate": "...", "loan_term": "...", "emi": "..." }}
- For a Terms of Service: {{ "company_name": "...", "governing_law": "...", "data_collection": "..." }}

**Part 2: Text Summary & Checklist**
Provide a clear, bulleted summary and a 3-4 point action checklist for the user.

DOCUMENT TEXT: "{document_text}"

RESPONSE:
"""

# 2. Risk Analysis Prompt (Unchanged)
RISK_ANALYSIS_PROMPT = """
You are a paralegal AI. Based on the following document text from India, identify potential risks, ambiguous clauses, or "gotcha" clauses for the primary user. List each risk with a simple explanation. If no significant risks are found, state that the document appears standard. Provide the entire response in the {language} language.
DOCUMENT TEXT: "{document_text}"
RISK ANALYSIS in {language}:
"""

# 3. "Questions to Ask" Prompt
QUESTIONS_TO_ASK_PROMPT = """
Based on the following list of identified risks from a legal document, generate a bulleted list of 3-4 polite, specific, and actionable questions the user should ask the other party (e.g., landlord, bank, service provider) to clarify these points. Provide the entire response in the {language} language.
IDENTIFIED RISKS: "{risk_analysis_text}"
QUESTIONS TO ASK in {language}:
"""

# 4. Stamp Duty Guidance Prompt
STAMP_DUTY_PROMPT = """
Based on this document being a {doc_type} from India, provide a short, general paragraph about the typical stamp duty and registration requirements. Start with a clear disclaimer that this is not legal advice and requirements vary by state. Provide the entire response in the {language} language.
GUIDANCE in {language}:
"""

# 5. Clause Deep Dive Prompt
ANALYZE_CLAUSE_PROMPT = """
Explain the following legal clause from an Indian contract in simple terms and highlight any potential risks for the user. Provide the entire response in the {language} language.
CLAUSE TEXT: "{clause_text}"
EXPLANATION AND RISKS in {language}:
"""

# 6. Document Comparison Prompt
COMPARE_PROMPT = """
You are an expert legal AI. Compare the two document texts below. Provide a bulleted list of the key differences, additions, and removals in "Document B" compared to "Document A". Focus on changes related to finances, dates, and responsibilities. Provide the entire response in the {language} language.
DOCUMENT A (Old): "{doc_a_text}"
DOCUMENT B (New): "{doc_b_text}"
COMPARISON ANALYSIS in {language}:
"""

# --- MAIN FLASK ROUTES ---

@app.route('/analyze', methods=['POST'])
def analyze_document():
    # ... (Authentication and form data retrieval is the same)
    try:
        id_token = request.headers['Authorization'].split(' ').pop()
        uid = auth.verify_id_token(id_token)['uid']
    except Exception: return jsonify({"error": "Unauthorized."}), 401
    
    file = request.files['document']
    doc_type = request.form.get('doc_type')
    language = request.form.get('language', 'English')
    filename = request.form.get('filename', 'Untitled')
    tags_string = request.form.get('tags', '')
    tags_array = [tag.strip().lower() for tag in tags_string.split(',') if tag.strip()]

    try:
        document_text = extract_text_from_pdf(file.stream)
        if not document_text or len(document_text.strip()) < 50:
             return jsonify({"error": "Could not extract sufficient text from this PDF."}), 400

        # --- MULTI-STEP AI ANALYSIS ---
        # Step 1: Get Main Analysis (JSON + Text Summary)
        main_prompt = MAIN_ANALYSIS_PROMPT.format(document_text=document_text, language=language)
        main_response = get_gemini_response(main_prompt)
        
        # Try to parse the JSON part from the response
        key_info_json = {}
        try:
            # Find the start and end of the JSON block
            json_start = main_response.find('{')
            json_end = main_response.rfind('}') + 1
            if json_start != -1 and json_end != -1:
                json_string = main_response[json_start:json_end]
                key_info_json = json.loads(json_string)
                # The rest of the text is the summary
                summary_and_checklist = main_response[json_end:].strip()
            else:
                summary_and_checklist = main_response # Fallback if JSON not found
        except json.JSONDecodeError:
            summary_and_checklist = main_response # Fallback if JSON is invalid

        # Step 2: Get Risk Analysis
        risk_prompt = RISK_ANALYSIS_PROMPT.format(document_text=document_text, language=language)
        risk_analysis = get_gemini_response(risk_prompt)
        
        # Step 3: Get "Questions to Ask" based on risks
        questions_prompt = QUESTIONS_TO_ASK_PROMPT.format(risk_analysis_text=risk_analysis, language=language)
        questions_to_ask = get_gemini_response(questions_prompt)
        
        # Step 4: Get Stamp Duty Guidance
        stamp_duty_prompt = STAMP_DUTY_PROMPT.format(doc_type=doc_type, language=language)
        stamp_duty_guidance = get_gemini_response(stamp_duty_prompt)
        
        # Step 5: Save everything to Firestore
        doc_ref = db.collection('users').document(uid).collection('documents').document()
        doc_ref.set({
            'filename': filename, 'doc_type': doc_type, 'language': language,
            'key_info': key_info_json, 'summary_and_checklist': summary_and_checklist,
            'risk_analysis': risk_analysis, 'questions_to_ask': questions_to_ask,
            'stamp_duty_guidance': stamp_duty_guidance,
            'tags': tags_array, 'analyzedAt': datetime.datetime.now(tz=datetime.timezone.utc),
        })

        # Step 6: Return all results to frontend
        return jsonify({
            "key_info": key_info_json, "summary_and_checklist": summary_and_checklist,
            "risk_analysis": risk_analysis, "questions_to_ask": questions_to_ask,
            "stamp_duty_guidance": stamp_duty_guidance, "doc_id": doc_ref.id,
        })
    except Exception as e:
        print(f"An error occurred in /analyze: {e}")
        return jsonify({"error": "An internal server error occurred."}), 500

# --- NEW ROUTES FOR NEW FEATURES ---
@app.route('/analyze_clause', methods=['POST'])
def analyze_clause():
    try:
        data = request.get_json()
        clause_text = data.get('clause_text')
        language = data.get('language', 'English')
        if not clause_text: return jsonify({"error": "Clause text is required."}), 400
        prompt = ANALYZE_CLAUSE_PROMPT.format(clause_text=clause_text, language=language)
        explanation = get_gemini_response(prompt)
        return jsonify({"explanation": explanation}), 200
    except Exception as e:
        print(f"Error in /analyze_clause: {e}")
        return jsonify({"error": "Could not analyze clause."}), 500

@app.route('/compare', methods=['POST'])
def compare():
    if 'doc_a' not in request.files or 'doc_b' not in request.files:
        return jsonify({"error": "Please upload both documents."}), 400
    language = request.form.get('language', 'English')
    try:
        doc_a_text = extract_text_from_pdf(request.files['doc_a'].stream)
        doc_b_text = extract_text_from_pdf(request.files['doc_b'].stream)
        if not doc_a_text or not doc_b_text:
            return jsonify({"error": "Could not extract text from one or both documents."}), 400
        prompt = COMPARE_PROMPT.format(doc_a_text=doc_a_text, doc_b_text=doc_b_text, language=language)
        comparison = get_gemini_response(prompt)
        return jsonify({"comparison": comparison}), 200
    except Exception as e:
        print(f"Error in /compare: {e}")
        return jsonify({"error": "Could not compare documents."}), 500

# --- Existing routes (share link, serve frontend) are unchanged ---
@app.route('/create_share_link', methods=['POST'])
# ... (function code is the same as before)
@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')
@app.route('/share.html')
def serve_share_page():
    return send_from_directory(app.static_folder, 'share.html')
if __name__ == '__main__':
    app.run(debug=True, port=5000)

