import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js";
import { getAuth, createUserWithEmailAndPassword, signInWithEmailAndPassword, onAuthStateChanged, signOut } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js";
import { getFirestore, collection, doc, getDoc, getDocs, query, where, orderBy } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-firestore.js";

const firebaseConfig = {
    apiKey: "AIzaSyA33tEkjkJjoZr0l-DNxwevv9phRA9GkjY",
    authDomain: "lexiguide-hackathon-2025.firebaseapp.com",
    projectId: "lexiguide-hackathon-2025",
    storageBucket: "lexiguide-hackathon-2025.firebasestorage.app",
    messagingSenderId: "814528861476",
    appId: "1:814528861476:web:7d3ce97018abd1a8dc0fb1",
    measurementId: "G-FHQW7RH75X"
};

const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const db = getFirestore(app);
let currentDocId = null;

// --- UI ELEMENTS ---
const authSection = document.getElementById('auth-section');
const appContent = document.getElementById('app-content');
const userInfo = document.getElementById('user-info');
const userEmailSpan = document.getElementById('user-email');
const loginContainer = document.getElementById('login-container');
const signupContainer = document.getElementById('signup-container');
const themeToggle = document.getElementById('theme-toggle');
const helpBtn = document.getElementById('help-btn');

// --- AUTH LOGIC ---
window.toggleAuthForms = function() {
    loginContainer.classList.toggle('hidden');
    signupContainer.classList.toggle('hidden');
}
onAuthStateChanged(auth, user => {
    if (user) {
        authSection.classList.add('hidden');
        appContent.classList.remove('hidden');
        userInfo.classList.remove('hidden');
        userEmailSpan.textContent = user.email;
        loadUserDocuments(user.uid);
        if (!localStorage.getItem('lexiguide_tour_completed')) {
            setTimeout(startTour, 1000);
        }
    } else {
        authSection.classList.remove('hidden');
        appContent.classList.add('hidden');
        userInfo.classList.add('hidden');
        userEmailSpan.textContent = '';
    }
});
document.getElementById('signup-button').addEventListener('click', () => {
    const email = document.getElementById('signup-email').value;
    const password = document.getElementById('signup-password').value;
    createUserWithEmailAndPassword(auth, email, password).catch(error => alert(error.message));
});
document.getElementById('login-button').addEventListener('click', () => {
    const email = document.getElementById('login-email').value;
    const password = document.getElementById('login-password').value;
    signInWithEmailAndPassword(auth, email, password).catch(error => alert(error.message));
});
document.getElementById('logout-button').addEventListener('click', () => {
    signOut(auth);
});

// --- CORE APP LOGIC ---
window.handleAnalyze = async function() {
    const user = auth.currentUser;
    if (!user) { alert("Please log in."); return; }
    const uploader = document.getElementById('doc-uploader');
    if (uploader.files.length === 0) { alert("Please select a PDF file."); return; }
    const file = uploader.files[0];
    const formData = new FormData();
    formData.append('document', file);
    formData.append('language', document.getElementById('language-selector').value);
    formData.append('filename', file.name);
    formData.append('tags', document.getElementById('tags-input').value);
    document.getElementById('loader').classList.remove('hidden');
    document.getElementById('results').classList.add('hidden');
    const uploadStatusP = document.getElementById('upload-status');
    if (uploadStatusP) uploadStatusP.textContent = 'Analyzing... this may take a moment.';
    try {
        const token = await user.getIdToken();
        const response = await fetch('/analyze', {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ' + token },
            body: formData
        });
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || "Analysis failed.");
        }
        const data = await response.json();
        currentDocId = data.doc_id;
        populateKeyInfoCard(data.key_info);
        document.getElementById('summary-text').textContent = data.summary_and_checklist;
        document.getElementById('risk-text').textContent = data.risk_analysis;
        document.getElementById('questions-text').textContent = data.questions_to_ask;
        document.getElementById('missing-clauses-text').textContent = data.missing_clauses;
        document.getElementById('stamp-duty-text').textContent = data.legal_formalities_guidance;
        makeAnalysisInteractive('summary-text');
        makeAnalysisInteractive('risk-text');
        document.getElementById('results').classList.remove('hidden');
        if (uploadStatusP) uploadStatusP.textContent = 'Analysis complete!';
        uploader.value = '';
        loadUserDocuments(user.uid);
    } catch (error) {
        alert("Error: " + error.message);
        if (uploadStatusP) uploadStatusP.textContent = '';
    } finally {
        document.getElementById('loader').classList.add('hidden');
    }
}
window.handleSearch = function() {
    const user = auth.currentUser;
    if (!user) return;
    const searchTerm = document.getElementById('search-input').value;
    loadUserDocuments(user.uid, searchTerm.trim().toLowerCase());
}
async function loadUserDocuments(userId, searchTerm = null) {
    const listElement = document.getElementById('past-analyses-list');
    listElement.innerHTML = "Loading history...";
    try {
        let documentsQuery;
        const documentsColRef = collection(db, 'users', userId, 'documents');
        if (searchTerm) {
            documentsQuery = query(documentsColRef, where("tags", "array-contains", searchTerm), orderBy('analyzedAt', 'desc'));
        } else {
            documentsQuery = query(documentsColRef, orderBy('analyzedAt', 'desc'));
        }
        const querySnapshot = await getDocs(documentsQuery);
        listElement.innerHTML = "";
        if (querySnapshot.empty) {
            listElement.innerHTML = `<p>No documents found${searchTerm ? ' with that tag' : ''}.</p>`;
            return;
        }
        querySnapshot.forEach(docSnap => {
            const docData = docSnap.data();
            const item = document.createElement('div');
            item.className = 'past-analysis-item';
            item.innerHTML = `
                <h4>${docData.filename} (${docData.doc_type})</h4>
                <p>Analyzed on: ${docData.analyzedAt.toDate().toLocaleString()}</p>
                ${docData.tags && docData.tags.length > 0 ? `<p>Jurisdiction: ${docData.jurisdiction || 'N/A'}<br>Tags: ${docData.tags.join(', ')}</p>` : ''}
                <button onclick="viewAnalysis('${docSnap.id}')">View Analysis</button>
            `;
            listElement.appendChild(item);
        });
    } catch(error) {
        console.error("Error loading documents:", error);
        listElement.innerHTML = "<p>Could not load document history.</p>";
    }
}
window.viewAnalysis = async function(docId) {
    const user = auth.currentUser;
    if (!user) return;
    const docRef = doc(db, 'users', user.uid, 'documents', docId);
    const docSnap = await getDoc(docRef);
    if (docSnap.exists()) {
        const data = docSnap.data();
        currentDocId = docId;
        populateKeyInfoCard(data.key_info);
        document.getElementById('summary-text').textContent = data.summary_and_checklist;
        document.getElementById('risk-text').textContent = data.risk_analysis;
        document.getElementById('questions-text').textContent = data.questions_to_ask;
        document.getElementById('missing-clauses-text').textContent = data.missing_clauses;
        document.getElementById('stamp-duty-text').textContent = data.legal_formalities_guidance || data.stamp_duty_guidance;
        makeAnalysisInteractive('summary-text');
        makeAnalysisInteractive('risk-text');
        document.getElementById('results').classList.remove('hidden');
        window.scrollTo(0, 0);
    } else {
        alert("Could not find analysis.");
    }
}
function populateKeyInfoCard(keyInfo) {
    const keyInfoCard = document.getElementById('key-info-card');
    keyInfoCard.innerHTML = '';
    if (!keyInfo || Object.keys(keyInfo).length === 0) {
        keyInfoCard.innerHTML = '<p>No structured key information was extracted.</p>';
        return;
    }
    const createScoreVisual = (score) => {
        let stars = '';
        for (let i = 0; i < 10; i++) {
            stars += i < score ? '★' : '☆';
        }
        return `<span style="color: #f0ad4e;">${stars}</span> (${score}/10)`;
    };
    for (const [key, value] of Object.entries(keyInfo)) {
        const item = document.createElement('div');
        item.className = 'info-item';
        const label = key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
        let displayValue = value;
        if (key === 'readability_score' || key === 'fairness_score') {
            displayValue = createScoreVisual(value);
        }
        item.innerHTML = `<span class="label">${label}</span><span class="value">${displayValue}</span>`;
        keyInfoCard.appendChild(item);
    }
}
window.handleExport = function() {
    const { jsPDF } = window.jspdf;
    const doc = new jsPDF();
    doc.text("LexiGuard - Document Analysis", 10, 10);
    doc.text("Summary & Action Plan", 10, 20);
    doc.text(document.getElementById('summary-text').innerText, 10, 30, { maxWidth: 180 });
    doc.addPage();
    doc.text("Risk Radar", 10, 10);
    doc.text(document.getElementById('risk-text').innerText, 10, 20, { maxWidth: 180 });
    doc.save("LexiGuide-Analysis.pdf");
}
window.handleShare = async function() {
    const user = auth.currentUser;
    if (!user || !currentDocId) {
        alert("Please view an analysis before sharing."); return;
    }
    try {
        const token = await user.getIdToken();
        const response = await fetch('/create_share_link', {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' },
            body: JSON.stringify({ doc_id: currentDocId })
        });
        if (!response.ok) {
            const errorData = await response.json(); throw new Error(errorData.error);
        }
        const data = await response.json();
        const shareLink = `${window.location.origin}/share.html?id=${data.share_id}`;
        prompt("Here is your shareable link:", shareLink);
    } catch (error) {
        alert("Could not create share link: " + error.message);
    }
}

// --- STANDALONE FEATURE LOGIC ---
window.handleClauseAnalyze = async function() {
    const clauseText = document.getElementById('clause-input').value;
    const language = document.getElementById('language-selector').value;
    if (!clauseText.trim()) { alert("Please paste a clause to analyze."); return; }
    const resultPre = document.getElementById('clause-result');
    resultPre.textContent = "Analyzing...";
    resultPre.classList.remove('hidden');
    try {
        const response = await fetch('/analyze_clause', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ clause_text: clauseText, language: language })
        });
        if (!response.ok) { throw new Error((await response.json()).error); }
        const data = await response.json();
        resultPre.textContent = data.explanation;
    } catch (error) {
        resultPre.textContent = "Error: " + error.message;
    }
}
window.handleCompare = async function() {
    const docAUploader = document.getElementById('doc-a-uploader');
    const docBUploader = document.getElementById('doc-b-uploader');
    if (docAUploader.files.length === 0 || docBUploader.files.length === 0) {
        alert("Please upload both documents."); return;
    }
    const formData = new FormData();
    formData.append('doc_a', docAUploader.files[0]);
    formData.append('doc_b', docBUploader.files[0]);
    formData.append('language', document.getElementById('language-selector').value);
    const resultPre = document.getElementById('compare-result');
    resultPre.textContent = "Comparing...";
    resultPre.classList.remove('hidden');
    try {
        const response = await fetch('/compare', { method: 'POST', body: formData });
        if (!response.ok) { throw new Error((await response.json()).error); }
        const data = await response.json();
        resultPre.textContent = data.comparison;
    } catch (error) {
        resultPre.textContent = "Error: " + error.message;
    }
}

// --- UI ENHANCEMENT LOGIC ---
const LEGAL_TERMS = ["indemnity", "escrow", "lessee", "lessor", "collateral", "tenure", "sublet", "arbitration", "liability", "jurisdiction", "notary", "stamp duty", "force majeure", "annexure", "perpetuity", "waiver"];
function makeAnalysisInteractive(elementId) {
    const element = document.getElementById(elementId);
    if (!element) return;
    let content = element.textContent;
    LEGAL_TERMS.forEach(term => {
        const regex = new RegExp(`\\b(${term})\\b`, 'gi');
        content = content.replace(regex, `<span class="legal-term" onclick="handleTermClick(this)">$1</span>`);
    });
    element.innerHTML = content;
}
window.handleTermClick = async function(element) {
    const term = element.innerText.toLowerCase();
    const language = document.getElementById('language-selector').value;
    try {
        const response = await fetch('/explain_term', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ term, language })
        });
        if (!response.ok) throw new Error("Could not fetch explanation.");
        const data = await response.json();
        alert(`"${term.charAt(0).toUpperCase() + term.slice(1)}"\n\n${data.explanation}`);
    } catch (error) {
        alert(`Could not get an explanation for "${term}".`);
    }
}
const currentTheme = localStorage.getItem('theme');
if (currentTheme) {
    document.documentElement.setAttribute('data-theme', currentTheme);
    if (currentTheme === 'dark') themeToggle.textContent = '☀️';
}
themeToggle.addEventListener('click', () => {
    let theme = document.documentElement.getAttribute('data-theme');
    if (theme === 'dark') {
        document.documentElement.removeAttribute('data-theme');
        localStorage.removeItem('theme');
        themeToggle.textContent = '🌙';
    } else {
        document.documentElement.setAttribute('data-theme', 'dark');
        localStorage.setItem('theme', 'dark');
        themeToggle.textContent = '☀️';
    }
});
const tourSteps = [
    { element: '#main-analyzer', title: 'Welcome to LexiGuard!', text: 'This is the main analysis tool. Let\'s quickly go over the key features.' },
    { element: '#tags-input', title: '1. Add Tags', text: 'Before uploading, add tags to organize and search for your documents later.' },
    { element: '#dashboard', title: '2. Document History', text: 'All your past analyses are saved here. You can search them by the tags you added.' },
    { element: '#clause-analyzer', title: '3. Clause Deep Dive', text: 'Have a specific, confusing clause? Paste it here for a focused analysis.' },
    { element: '#document-comparer', title: '4. Compare Documents', text: 'Upload two versions of a document to see exactly what has changed.' },
    { element: '#theme-toggle', title: 'Toggle Theme', text: 'Finally, you can switch between light and dark mode anytime.' }
];
function showTourStep(index) {
    const existingTourStep = document.querySelector('.tour-step');
    if (existingTourStep) existingTourStep.remove();
    if (index >= tourSteps.length) { localStorage.setItem('lexiguide_tour_completed', 'true'); return; }
    const step = tourSteps[index];
    const targetElement = document.querySelector(step.element);
    if (!targetElement) return;
    const tourStepDiv = document.createElement('div');
    tourStepDiv.className = 'tour-step';
    const targetRect = targetElement.getBoundingClientRect();
    let top = targetRect.bottom + 10;
    let left = targetRect.left;
    if ((top + 180) > window.innerHeight) { top = targetRect.top - 190; }
    if (left < 10) { left = 10; }
    if ((left + 350) > window.innerWidth) { left = window.innerWidth - 360; }
    tourStepDiv.style.left = `${left}px`;
    tourStepDiv.style.top = `${top}px`;
    tourStepDiv.innerHTML = `
        <h4>${step.title}</h4><p>${step.text}</p>
        <div class="tour-nav">
            <button id="tour-prev" ${index === 0 ? 'disabled' : ''}>Prev</button>
            <button id="tour-next">${index === tourSteps.length - 1 ? 'Finish' : 'Next'}</button>
        </div>`;
    document.body.appendChild(tourStepDiv);
    document.getElementById('tour-next').onclick = () => showTourStep(index + 1);
    if(index > 0) document.getElementById('tour-prev').onclick = () => showTourStep(index - 1);
}
function startTour() { showTourStep(0); }
helpBtn.addEventListener('click', startTour);
