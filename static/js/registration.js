document.addEventListener("DOMContentLoaded", function () {

    // INDEX / HOME PAGE → Apply Now
    const applyBtn = document.getElementById("applyBtn");
    if (applyBtn) {
        applyBtn.addEventListener("click", function (e) {
            e.preventDefault();
            handleRegistrationClick("/instruction");
        });
    }

    // LOGIN PAGE → Register Here
    const registerLink = document.getElementById("registerLink");
    if (registerLink) {
        registerLink.addEventListener("click", function (e) {
            e.preventDefault();
            handleRegistrationClick("/instruction");
        });
    }

});


/* ---------- MAIN REGISTRATION CHECK ---------- */
function handleRegistrationClick(redirectUrl) {

    const now = new Date();

    // 🔧 CHANGE DATES ONLY HERE
    const registrationStart = new Date("2026-02-01T00:00:00");
    const registrationEnd   = new Date("2026-05-28T23:59:59");

    // ✅ Check if current date is within range
    if (now >= registrationStart && now <= registrationEnd) {
        // ✅ Registration Open → Redirect
        window.location.href = redirectUrl;
    } else {
        // ❌ Registration Closed → Show Modal
        openModal();
    }
}


/* ---------- MODAL CONTROLS ---------- */
function openModal() {
    const modal = document.getElementById("closedModal");
    if (modal) {
        modal.style.display = "flex";
    } else {
        console.warn("Modal element with ID 'closedModal' not found");
    }
}

function closeModal() {
    const modal = document.getElementById("closedModal");
    if (modal) {
        modal.style.display = "none";
    }
}