import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js";
import { getFirestore, doc, getDoc } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-firestore.js";

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
const db = getFirestore(app);

async function loadSharedAnalysis() {
    const params = new URLSearchParams(window.location.search);
    const shareId = params.get('id');
    if (!shareId) {
        document.getElementById('filename').textContent = "Error: No Share ID provided.";
        return;
    }
    try {
        const docRef = doc(db, 'shared_analyses', shareId);
        const docSnap = await getDoc(docRef);
        if (docSnap.exists()) {
            const data = docSnap.data();
            document.getElementById('filename').textContent = data.filename || "Shared Analysis";
            document.getElementById('doc-type').textContent = `Document Type: ${data.doc_type}`;
            document.getElementById('summary-text').textContent = data.summary_and_checklist;
            document.getElementById('risk-text').textContent = data.risk_analysis;
        } else {
            document.getElementById('filename').textContent = "Error: This shared analysis could not be found or has been deleted.";
        }
    } catch (error) {
        console.error("Error loading shared analysis:", error);
        document.getElementById('filename').textContent = "An error occurred while loading the analysis.";
    }
}
loadSharedAnalysis();
