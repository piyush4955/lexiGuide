import os
import datetime
import uuid
import json
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv
import google.generativeai as genai
import pdfplumber

# Firebase Admin imports
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
        cleaned_text = response.text.strip().replace('```json', '').replace('```', '').strip()
        return cleaned_text
    except Exception as e:
        print(f"Gemini API Error: {e}")
        return f"Sorry, there was an error with the AI model: {e}"

# --- PROMPT TEMPLATES ---
MAIN_ANALYSIS_PROMPT = """
Analyze the following legal document from India. Provide a multi-part response in the {language} language.

**Part 1: Key Information JSON**
Extract the most critical data points into a valid JSON object. The keys should be in English. For any value not found, use "Not specified".
- Add a 'readability_score' (1-10, 10=very easy to read) and a 'fairness_score' (1-10, 10=very fair for all parties) with a brief 'score_justification'.
- For a Rental Agreement: {{ "readability_score": ..., "fairness_score": ..., "score_justification": "...", "parties": "...", "rent_amount": "...", "security_deposit": "...", "lease_duration": "..." }}
- For a Loan Contract: {{ "readability_score": ..., "fairness_score": ..., "score_justification": "...", "parties": "...", "loan_amount": "...", "interest_rate": "..." }}
- For a Terms of Service: {{ "readability_score": ..., "fairness_score": ..., "score_justification": "...", "company_name": "...", "governing_law": "..." }}

**Part 2: Text Summary & Checklist**
Provide a clear, bulleted summary and a 3-4 point action checklist for the user.

DOCUMENT TEXT: "{document_text}"
RESPONSE:
"""
RISK_ANALYSIS_PROMPT = """
You are a paralegal AI. Based on the following document text from India, identify potential risks, ambiguous clauses, or "gotcha" clauses for the primary user. List each risk with a simple explanation. If no significant risks are found, state that the document appears to be standard. Provide the entire response in the {language} language.
DOCUMENT TEXT: "{document_text}"
RISK ANALYSIS in {language}:
"""
QUESTIONS_TO_ASK_PROMPT = """
Based on the following list of identified risks from a legal document, generate a bulleted list of 3-4 polite, specific, and actionable questions the user should ask the other party (e.g., landlord, bank, service provider) to clarify these points. Provide the entire response in the {language} language.
IDENTIFIED RISKS: "{risk_analysis_text}"
QUESTIONS TO ASK in {language}:
"""
STAMP_DUTY_PROMPT = """
Based on this document being a {doc_type} from India, provide a short, general paragraph about the typical stamp duty and registration requirements. Start with a clear disclaimer that this is not legal advice and requirements vary by state. Provide the entire response in the {language} language.
GUIDANCE in {language}:
"""
MISSING_CLAUSES_PROMPT = """
You are an expert Indian legal assistant. Based on the document text being a standard Indian {doc_type}, what are the top 3-4 standard legal clauses that are surprisingly MISSING from the text? This is very important. For each missing clause, briefly explain why it's usually included. If nothing significant is missing, state that the document appears to be comprehensive. Provide the entire response in the {language} language.
DOCUMENT TEXT: "{document_text}"
MISSING CLAUSES ANALYSIS in {language}:
"""
ANALYZE_CLAUSE_PROMPT = """
Explain the following legal clause from an Indian contract in simple terms and highlight any potential risks for the user. Provide the entire response in the {language} language.
CLAUSE TEXT: "{clause_text}"
EXPLANATION AND RISKS in {language}:
"""
COMPARE_PROMPT = """
You are an expert legal AI. Compare the two document texts below. Provide a bulleted list of the key differences, additions, and removals in "Document B" compared to "Document A". Focus on changes related to finances, dates, and responsibilities. Provide the entire response in the {language} language.
DOCUMENT A (Old): "{doc_a_text}"
DOCUMENT B (New): "{doc_b_text}"
COMPARISON ANALYSIS in {language}:
"""
EXPLAIN_TERM_PROMPT = """
You are an AI legal assistant. Explain the following legal term in one simple sentence, as you would to a non-lawyer in India.
Provide the entire response in the {language} language.
LEGAL TERM: "{term}"
SIMPLE EXPLANATION:
"""

# --- FLASK ROUTES ---

@app.route('/analyze', methods=['POST'])
def analyze_document():
    try:
        id_token = request.headers['Authorization'].split(' ').pop()
        uid = auth.verify_id_token(id_token)['uid']
    except Exception: return jsonify({"error": "Unauthorized."}), 401
    
    if 'document' not in request.files: return jsonify({"error": "No file part"}), 400
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

        main_prompt = MAIN_ANALYSIS_PROMPT.format(document_text=document_text, language=language)
        main_response = get_gemini_response(main_prompt)
        
        key_info_json, summary_and_checklist = {}, main_response
        try:
            json_start = main_response.find('{')
            json_end = main_response.rfind('}') + 1
            if json_start != -1 and json_end != -1:
                json_string = main_response[json_start:json_end]
                key_info_json = json.loads(json_string)
                summary_and_checklist = main_response[json_end:].strip()
        except Exception as e:
            print(f"JSON parsing error: {e}")

        risk_prompt = RISK_ANALYSIS_PROMPT.format(document_text=document_text, language=language)
        risk_analysis = get_gemini_response(risk_prompt)
        
        questions_prompt = QUESTIONS_TO_ASK_PROMPT.format(risk_analysis_text=risk_analysis, language=language)
        questions_to_ask = get_gemini_response(questions_prompt)
        
        stamp_duty_prompt = STAMP_DUTY_PROMPT.format(doc_type=doc_type, language=language)
        stamp_duty_guidance = get_gemini_response(stamp_duty_prompt)
        
        missing_clauses_prompt = MISSING_CLAUSES_PROMPT.format(doc_type=doc_type, document_text=document_text, language=language)
        missing_clauses = get_gemini_response(missing_clauses_prompt)

        doc_ref = db.collection('users').document(uid).collection('documents').document()
        doc_ref.set({
            'filename': filename, 'doc_type': doc_type, 'language': language,
            'key_info': key_info_json, 'summary_and_checklist': summary_and_checklist,
            'risk_analysis': risk_analysis, 'questions_to_ask': questions_to_ask,
            'stamp_duty_guidance': stamp_duty_guidance, 'missing_clauses': missing_clauses,
            'tags': tags_array, 'analyzedAt': datetime.datetime.now(tz=datetime.timezone.utc),
        })

        return jsonify({
            "key_info": key_info_json, "summary_and_checklist": summary_and_checklist,
            "risk_analysis": risk_analysis, "questions_to_ask": questions_to_ask,
            "stamp_duty_guidance": stamp_duty_guidance, "missing_clauses": missing_clauses,
            "doc_id": doc_ref.id,
        })
    except Exception as e:
        print(f"An error occurred in /analyze: {e}")
        return jsonify({"error": "An internal server error occurred."}), 500

@app.route('/create_share_link', methods=['POST'])
def create_share_link():
    try:
        id_token = request.headers['Authorization'].split(' ').pop()
        uid = auth.verify_id_token(id_token)['uid']
    except Exception: return jsonify({"error": "Unauthorized request."}), 401
    try:
        doc_id = request.get_json().get('doc_id')
        if not doc_id: return jsonify({"error": "Document ID is required."}), 400
        original_doc = db.collection('users').document(uid).collection('documents').document(doc_id).get()
        if not original_doc.exists: return jsonify({"error": "Original analysis not found."}), 404
        analysis_data = original_doc.to_dict()
        share_id = str(uuid.uuid4())
        share_ref = db.collection('shared_analyses').document(share_id)
        share_ref.set({
            'summary_and_checklist': analysis_data.get('summary_and_checklist'),
            'risk_analysis': analysis_data.get('risk_analysis'), 'filename': analysis_data.get('filename'),
            'doc_type': analysis_data.get('doc_type'), 'createdAt': datetime.datetime.now(tz=datetime.timezone.utc),
        })
        return jsonify({"share_id": share_id}), 200
    except Exception as e:
        print(f"Error creating share link: {e}")
        return jsonify({"error": "Could not create share link."}), 500

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

@app.route('/explain_term', methods=['POST'])
def explain_term():
    try:
        data = request.get_json()
        term = data.get('term')
        language = data.get('language', 'English')
        if not term: return jsonify({"error": "A term is required."}), 400
        prompt = EXPLAIN_TERM_PROMPT.format(term=term, language=language)
        explanation = get_gemini_response(prompt)
        return jsonify({"explanation": explanation}), 200
    except Exception as e:
        print(f"Error explaining term: {e}")
        return jsonify({"error": "Could not get an explanation."}), 500

@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/share.html')
def serve_share_page():
    return send_from_directory(app.static_folder, 'share.html')

if __name__ == '__main__':
    app.run(debug=True, port=5000)