// ===== STATE =====
let selectedRole = "";
let selectedInterests = new Set(["ai / machine learning"]);
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let callTimerInterval = null;
let callSeconds = 0;
let briefingAudioB64 = null;
let briefingArticles = [];
let currentAudio = null;
let analyserNode = null;
let audioContext = null;
let micStream = null;

// ===== PROFILE SCREEN =====

// Role chips
document.querySelectorAll(".role-chip").forEach(chip => {
    chip.addEventListener("click", () => {
        document.querySelectorAll(".role-chip").forEach(c => c.classList.remove("selected"));
        chip.classList.add("selected");
        selectedRole = chip.dataset.role;
    });
});

// Interest chips
document.querySelectorAll(".interest-chip").forEach(chip => {
    chip.addEventListener("click", () => {
        chip.classList.toggle("selected");
        const interest = chip.dataset.interest;
        if (selectedInterests.has(interest)) {
            selectedInterests.delete(interest);
        } else {
            selectedInterests.add(interest);
        }
    });
});

// ===== START EXPERIENCE =====
async function startExperience() {
    const name = document.getElementById("input-name").value.trim();
    if (!name) {
        document.getElementById("input-name").style.borderColor = "#e17055";
        document.getElementById("input-name").focus();
        return;
    }
    if (!selectedRole) {
        alert("Please select your role!");
        return;
    }

    const btn = document.getElementById("btn-start");
    btn.disabled = true;
    btn.textContent = "Setting up...";

    try {
        // Set profile
        await fetch("/api/profile", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                name: name,
                role: selectedRole,
                interests: Array.from(selectedInterests),
                preferred_depth: "medium",
            }),
        });

        // Switch to loading screen
        showScreen("screen-loading");

        // Animate pipeline steps
        await animatePipelineSteps();

        // Start briefing
        const resp = await fetch("/api/start-briefing", { method: "POST" });
        if (!resp.ok) throw new Error("Pipeline failed");

        const data = await resp.json();
        briefingAudioB64 = data.audio_base64;
        briefingArticles = data.articles || [];

        // Complete loading animation
        document.querySelectorAll(".step").forEach(s => s.classList.add("done"));
        document.getElementById("loading-text").textContent = "Ready!";

        await sleep(800);

        // Switch to call screen
        showScreen("screen-call");
        startCallTimer();

        // Add greeting message
        addMessage("system", "Call connected. Your briefing is ready.");
        addMessage("ai", data.summary_text.substring(0, 200) + "...");

        // Populate articles panel
        renderArticles(data.articles);

        // Auto-play briefing
        setTimeout(() => playBriefing(), 500);

    } catch (err) {
        console.error(err);
        alert("Something went wrong: " + err.message);
        btn.disabled = false;
        btn.textContent = "Start My Briefing →";
        showScreen("screen-profile");
    }
}

async function animatePipelineSteps() {
    const steps = ["step-1", "step-2", "step-3", "step-4", "step-5"];
    for (let i = 0; i < steps.length; i++) {
        const el = document.getElementById(steps[i]);
        el.classList.add("active");
        if (i > 0) {
            document.getElementById(steps[i - 1]).classList.remove("active");
            document.getElementById(steps[i - 1]).classList.add("done");
        }
        // Don't wait on last step — the actual API call is running
        if (i < steps.length - 1) await sleep(600);
    }
}

// ===== CALL SCREEN =====

function startCallTimer() {
    callSeconds = 0;
    callTimerInterval = setInterval(() => {
        callSeconds++;
        const mins = String(Math.floor(callSeconds / 60)).padStart(2, "0");
        const secs = String(callSeconds % 60).padStart(2, "0");
        document.getElementById("call-timer").textContent = `${mins}:${secs}`;
    }, 1000);
}

function endCall() {
    if (callTimerInterval) clearInterval(callTimerInterval);
    if (currentAudio) { currentAudio.pause(); currentAudio = null; }
    if (micStream) { micStream.getTracks().forEach(t => t.stop()); micStream = null; }
    fetch("/api/reset", { method: "POST" });
    showScreen("screen-profile");
    document.getElementById("btn-start").disabled = false;
    document.getElementById("btn-start").innerHTML = 'Start My Briefing <span class="btn-arrow">→</span>';
    document.getElementById("transcript-area").innerHTML = '<div class="transcript-placeholder">Your conversation will appear here...</div>';
    callSeconds = 0;
}

// ===== VOICE RECORDING =====

async function startRecording() {
    if (isRecording) return;

    try {
        micStream = await navigator.mediaDevices.getUserMedia({ audio: true });

        // Set up audio context for waveform
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const source = audioContext.createMediaStreamSource(micStream);
        analyserNode = audioContext.createAnalyser();
        analyserNode.fftSize = 256;
        source.connect(analyserNode);

        mediaRecorder = new MediaRecorder(micStream, { mimeType: "audio/webm" });
        audioChunks = [];

        mediaRecorder.ondataavailable = (e) => {
            if (e.data.size > 0) audioChunks.push(e.data);
        };

        mediaRecorder.start();
        isRecording = true;

        document.getElementById("btn-mic").classList.add("recording");
        document.getElementById("ai-label").textContent = "Listening...";
        document.getElementById("call-status").textContent = "Listening";
        document.getElementById("call-status").style.color = "#e17055";

        drawWaveform();
    } catch (err) {
        console.error("Mic error:", err);
        addMessage("system", "Could not access microphone. Please allow mic permission.");
    }
}

function stopRecording() {
    if (!isRecording || !mediaRecorder) return;

    mediaRecorder.stop();
    isRecording = false;

    document.getElementById("btn-mic").classList.remove("recording");
    document.getElementById("ai-label").textContent = "Processing...";
    document.getElementById("call-status").textContent = "Processing";
    document.getElementById("call-status").style.color = "var(--yellow)";

    // Stop mic stream
    if (micStream) {
        micStream.getTracks().forEach(t => t.stop());
        micStream = null;
    }

    mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunks, { type: "audio/webm" });

        // Show processing indicator
        addProcessingIndicator();

        // Convert to base64 and send
        const reader = new FileReader();
        reader.onloadend = async () => {
            const base64 = reader.result.split(",")[1];
            await sendAudioToBackend(base64);
        };
        reader.readAsDataURL(audioBlob);
    };
}

async function sendAudioToBackend(audioB64) {
    try {
        const resp = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ audio_base64: audioB64 }),
        });

        if (!resp.ok) throw new Error("Chat API error");

        const data = await resp.json();

        // Remove processing indicator
        removeProcessingIndicator();

        // Show transcript
        if (data.transcript) {
            addMessage("user", data.transcript);
        }

        addMessage("ai", data.text);

        // Play audio response
        playBase64Audio(data.audio_base64);

    } catch (err) {
        console.error("Chat error:", err);
        removeProcessingIndicator();
        addMessage("system", "Something went wrong. Try again.");
        setIdleState();
    }
}

// ===== TEXT INPUT (fallback) =====
document.addEventListener("keydown", (e) => {
    // Press 'T' to type when on call screen
    if (e.key === "t" && document.getElementById("screen-call").classList.contains("active") && !isRecording) {
        const text = prompt("Type your question:");
        if (text) sendTextToBackend(text);
    }
});

async function sendTextToBackend(text) {
    addMessage("user", text);
    addProcessingIndicator();

    document.getElementById("ai-label").textContent = "Thinking...";

    try {
        const resp = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: text }),
        });

        const data = await resp.json();
        removeProcessingIndicator();
        addMessage("ai", data.text);
        playBase64Audio(data.audio_base64);
    } catch (err) {
        removeProcessingIndicator();
        addMessage("system", "Error getting response.");
        setIdleState();
    }
}

// ===== AUDIO PLAYBACK =====

function playBase64Audio(b64) {
    if (!b64) { setIdleState(); return; }

    const bytes = atob(b64);
    const arr = new Uint8Array(bytes.length);
    for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
    const blob = new Blob([arr], { type: "audio/mp3" });
    const url = URL.createObjectURL(blob);

    if (currentAudio) { currentAudio.pause(); }

    currentAudio = new Audio(url);

    document.getElementById("ai-avatar").classList.add("speaking");
    document.getElementById("ai-label").textContent = "AI is speaking...";
    document.getElementById("call-status").textContent = "AI Speaking";
    document.getElementById("call-status").style.color = "var(--purple-light)";

    // Draw playback waveform
    drawPlaybackWaveform();

    currentAudio.onended = () => {
        document.getElementById("ai-avatar").classList.remove("speaking");
        setIdleState();
        URL.revokeObjectURL(url);
    };

    currentAudio.play().catch(err => {
        console.error("Playback error:", err);
        setIdleState();
    });
}

function playBriefing() {
    if (briefingAudioB64) {
        addMessage("system", "Playing your personalized briefing...");
        playBase64Audio(briefingAudioB64);
    }
}

function setIdleState() {
    document.getElementById("ai-label").textContent = "Hold mic to speak";
    document.getElementById("call-status").textContent = "Connected";
    document.getElementById("call-status").style.color = "var(--green)";
}

// ===== WAVEFORM =====

function drawWaveform() {
    const canvas = document.getElementById("waveform");
    const ctx = canvas.getContext("2d");

    function draw() {
        if (!isRecording || !analyserNode) return;

        const bufferLength = analyserNode.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);
        analyserNode.getByteTimeDomainData(dataArray);

        ctx.clearRect(0, 0, canvas.width, canvas.height);

        ctx.lineWidth = 2;
        ctx.strokeStyle = "#6c5ce7";
        ctx.beginPath();

        const sliceWidth = canvas.width / bufferLength;
        let x = 0;

        for (let i = 0; i < bufferLength; i++) {
            const v = dataArray[i] / 128.0;
            const y = (v * canvas.height) / 2;
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
            x += sliceWidth;
        }

        ctx.lineTo(canvas.width, canvas.height / 2);
        ctx.stroke();

        requestAnimationFrame(draw);
    }

    draw();
}

function drawPlaybackWaveform() {
    const canvas = document.getElementById("waveform");
    const ctx = canvas.getContext("2d");
    let frame = 0;

    function draw() {
        if (!currentAudio || currentAudio.paused) {
            // Clear and draw flat line
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.strokeStyle = "#2a2a3e";
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(0, canvas.height / 2);
            ctx.lineTo(canvas.width, canvas.height / 2);
            ctx.stroke();
            return;
        }

        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.lineWidth = 2;
        ctx.strokeStyle = "#a29bfe";
        ctx.beginPath();

        const bars = 50;
        const barWidth = canvas.width / bars;

        for (let i = 0; i < bars; i++) {
            const amp = Math.sin((i + frame) * 0.3) * 20 + Math.random() * 15;
            const y = canvas.height / 2;
            ctx.moveTo(i * barWidth + barWidth / 2, y - amp);
            ctx.lineTo(i * barWidth + barWidth / 2, y + amp);
        }

        ctx.stroke();
        frame++;
        requestAnimationFrame(draw);
    }

    draw();
}

// ===== TRANSCRIPT =====

function addMessage(type, text) {
    const area = document.getElementById("transcript-area");

    // Remove placeholder
    const placeholder = area.querySelector(".transcript-placeholder");
    if (placeholder) placeholder.remove();

    const div = document.createElement("div");
    div.className = `msg msg-${type}`;
    div.textContent = text;
    area.appendChild(div);

    // Scroll to bottom
    area.scrollTop = area.scrollHeight;
}

function addProcessingIndicator() {
    const area = document.getElementById("transcript-area");
    const div = document.createElement("div");
    div.className = "msg msg-ai";
    div.id = "processing-indicator";
    div.innerHTML = '<div class="processing-dots"><span></span><span></span><span></span></div>';
    area.appendChild(div);
    area.scrollTop = area.scrollHeight;
}

function removeProcessingIndicator() {
    const el = document.getElementById("processing-indicator");
    if (el) el.remove();
}

// ===== ARTICLES PANEL =====

function renderArticles(articles) {
    const list = document.getElementById("articles-list");
    list.innerHTML = "";

    if (!articles || articles.length === 0) {
        list.innerHTML = '<p style="color: var(--text-muted); text-align: center; padding: 2rem;">No articles yet.</p>';
        return;
    }

    articles.forEach((a, i) => {
        const card = document.createElement("div");
        card.className = "article-card";
        card.innerHTML = `
            <h4>${i + 1}. ${a.title}</h4>
            <div class="article-meta">
                <span>${a.source}</span>
                <span>${a.sentiment}</span>
            </div>
            <p style="font-size: 0.8rem; color: var(--text-dim);">${a.description}</p>
            ${a.why_it_matters ? `<p class="article-why">"${a.why_it_matters}"</p>` : ""}
            <div class="relevance-bar">
                <div class="relevance-fill" style="width: ${(a.relevance_score || 0.5) * 100}%"></div>
            </div>
        `;

        // Click to ask about article
        card.style.cursor = "pointer";
        card.addEventListener("click", () => {
            hideArticles();
            sendTextToBackend(`Tell me more about article ${i + 1}: ${a.title}`);
        });

        list.appendChild(card);
    });
}

function showArticles() {
    document.getElementById("articles-panel").classList.add("open");
}

function hideArticles() {
    document.getElementById("articles-panel").classList.remove("open");
}

// ===== UTILITIES =====

function showScreen(id) {
    document.querySelectorAll(".screen").forEach(s => s.classList.remove("active"));
    document.getElementById(id).classList.add("active");
}

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}
