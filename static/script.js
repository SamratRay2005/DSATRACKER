// Function to Toggle Solved/Bookmarked
async function toggleStatus(questionId, field, btnElement = null, weekNum = null) {
    // If solving, use checkbox state; else undefined
    let isChecked = undefined;
    
    // --- OPTIMISTIC UI UPDATE START ---
    // Store original state for rollback
    const originalState = {
        xpText: document.getElementById('user-xp')?.innerText,
        progressWidth: weekNum ? document.getElementById(`progress-bar-${weekNum}`)?.style.width : null,
        progressText: weekNum ? document.getElementById(`progress-text-${weekNum}`)?.innerText : null,
        starText: (field === 'bookmarked' && btnElement) ? (btnElement.querySelector('span') || btnElement).innerText : null
    };

    try {
        let isAdding = false; // Are we adding or removing?

        if (field === 'solved' && btnElement) {
            isChecked = btnElement.checked;
            isAdding = isChecked;

            // 1. Instant XP Update
            const xpEl = document.getElementById('user-xp');
            if (xpEl) {
                let currentXP = parseInt(xpEl.innerText.replace(/\D/g, '')) || 0;
                currentXP += isAdding ? 100 : -100;
                xpEl.innerText = `${currentXP} XP`;
            }

            // 2. Instant Progress Bar Update
            if (weekNum) {
                const textEl = document.getElementById(`progress-text-${weekNum}`);
                const barEl = document.getElementById(`progress-bar-${weekNum}`);
                
                if (textEl && barEl) {
                    const parts = textEl.innerText.split('/'); // "5/10"
                    let completed = parseInt(parts[0]);
                    const total = parseInt(parts[1]);
                    
                    completed += isAdding ? 1 : -1;
                    // Clamp
                    if (completed < 0) completed = 0;
                    if (completed > total) completed = total;
                    
                    textEl.innerText = `${completed}/${total}`;
                    
                    const percent = total > 0 ? (completed / total) * 100 : 0;
                    barEl.style.width = `${percent}%`;

                    // 3. Instant System Integrity Update (Sidebar)
                    const integrityTextEl = document.getElementById(`integrity-text-${weekNum}`);
                    const integrityBarEl = document.getElementById(`integrity-bar-${weekNum}`);
                    
                    if (integrityTextEl && integrityBarEl) {
                        const intPercent = Math.floor(percent);
                        integrityTextEl.innerText = `${intPercent}%`;
                        integrityBarEl.style.width = `${percent}%`;
                        
                        // Update colors for 100%
                        if (intPercent === 100) {
                            integrityTextEl.classList.remove('text-neon-blue');
                            integrityTextEl.classList.add('text-neon-green');
                            
                            integrityBarEl.classList.remove('bg-neon-blue', 'shadow-neon-blue');
                            integrityBarEl.classList.add('bg-neon-green', 'shadow-neon-green');
                        } else {
                            integrityTextEl.classList.add('text-neon-blue');
                            integrityTextEl.classList.remove('text-neon-green');
                            
                            integrityBarEl.classList.add('bg-neon-blue', 'shadow-neon-blue');
                            integrityBarEl.classList.remove('bg-neon-green', 'shadow-neon-green');
                        }
                    }
                }
            }
        } 
        else if (field === 'bookmarked' && btnElement) {
            // Toggle star immediately
            const starSpan = btnElement.querySelector('span') || btnElement;
            const isCurrentlyBookmarked = starSpan.innerText.trim() === '★';
            isAdding = !isCurrentlyBookmarked; // If it was star, we are removing
            
            starSpan.innerText = isAdding ? '★' : '☆';
            
            if (isAdding) {
                btnElement.classList.remove('text-gray-400', 'hover:text-yellow-300');
                btnElement.classList.add('text-yellow-400', 'drop-shadow-[0_0_10px_rgba(250,204,21,0.6)]');
            } else {
                btnElement.classList.remove('text-yellow-400', 'drop-shadow-[0_0_10px_rgba(250,204,21,0.6)]');
                btnElement.classList.add('text-gray-400', 'hover:text-yellow-300');
            }
        }
        // --- OPTIMISTIC UI UPDATE END ---

        const response = await fetch('/api/toggle', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ 
                question_id: questionId, 
                field: field,
                // Pass the intended state if available, so server can force sync
                set_to_solved: isChecked 
            })
        });
        const data = await response.json();
        
        // Use server data to correct if somehow drift happened, or just trust the optimistic update
        // We can optionally reconcile here if needed, but usually not needed for simple counters

        // Update Streak (Server authority is better for streak logic)
        const streakEl = document.getElementById('user-streak');
        if (streakEl && data.new_streak !== undefined) {
             streakEl.innerText = data.new_streak;
        }

    } catch (error) {
        console.error('Error:', error);
        
        // --- ROLLBACK ON ERROR ---
        if (field === 'solved' && btnElement) {
            btnElement.checked = !btnElement.checked;
            
            if (originalState.xpText) document.getElementById('user-xp').innerText = originalState.xpText;
            if (weekNum && originalState.progressWidth) document.getElementById(`progress-bar-${weekNum}`).style.width = originalState.progressWidth;
            if (weekNum && originalState.progressText) document.getElementById(`progress-text-${weekNum}`).innerText = originalState.progressText;
        }
        if (field === 'bookmarked' && btnElement) {
             // Rollback styles manually or just text
             const starSpan = btnElement.querySelector('span') || btnElement;
             starSpan.innerText = originalState.starText;
             // (Simplified style rollback)
             btnElement.classList.toggle('text-yellow-400');
             btnElement.classList.toggle('text-gray-400');
        }
    }
}

let currentMode = 'any';

// Function to Pick Random Question (In-View)
async function pickRandom(mode) {
    currentMode = mode;
    try {
        const response = await fetch(`/api/random?mode=${mode}`);
        const data = await response.json();
        
        if (data.error) {
            alert(data.error);
            return;
        }
        
        // Hide Schedule, Show Random View (inside Main area)
        document.getElementById('schedule-view').classList.add('hidden');
        document.getElementById('random-view').classList.remove('hidden');
        
        // Populate Data
        document.getElementById('fs-problem-name').innerText = data.name;
        document.getElementById('fs-topic').innerText = data.topic;
        document.getElementById('fs-difficulty').innerText = data.difficulty;
        document.getElementById('fs-link').href = data.link;

        // --- NEW: Handle Checkbox and Star ---
        const solvedCheckbox = document.getElementById('fs-solved');
        const bookmarkBtn = document.getElementById('fs-bookmark');
        const starIcon = document.getElementById('fs-star');

        // Set initial state from server
        solvedCheckbox.checked = data.solved;
        starIcon.innerText = data.bookmarked ? '★' : '☆';

        // Clear old event listeners to prevent duplicates (cloning usually works best)
        const newSolved = solvedCheckbox.cloneNode(true);
        solvedCheckbox.parentNode.replaceChild(newSolved, solvedCheckbox);
        
        const newBookmark = bookmarkBtn.cloneNode(true);
        bookmarkBtn.parentNode.replaceChild(newBookmark, bookmarkBtn);

        // Re-select fresh elements
        const currentSolved = document.getElementById('fs-solved');
        const currentBookmark = document.getElementById('fs-bookmark');
        const currentStar = document.querySelector('#fs-bookmark span'); // The star inside new button

        // Bind Click Events with current Question ID
        currentSolved.addEventListener('change', () => {
             toggleStatus(data.id, 'solved', currentSolved, data.week);
        });

        currentBookmark.addEventListener('click', () => {
             toggleStatus(data.id, 'bookmarked', currentStar);
        });
        
        // Color coding for difficulty (Cyberpunk)
        const diffEl = document.getElementById('fs-difficulty');
        diffEl.className = 'border px-4 py-1.5 rounded text-sm font-mono'; // Reset class base
        if(data.difficulty.includes('Easy')) {
            diffEl.classList.add('bg-green-500', 'text-green-400', 'border-green-500/30', 'bg-opacity-20');
        } else if(data.difficulty.includes('Medium')) {
           diffEl.classList.add('bg-yellow-500', 'text-yellow-400', 'border-yellow-500/30', 'bg-opacity-20');
        } else {
           diffEl.classList.add('bg-red-500', 'text-red-400', 'border-red-500/30', 'bg-opacity-20');
        }
        
    } catch (error) {
        console.error('Error fetching random:', error);
    }
}

function closeRandomView() {
    document.getElementById('random-view').classList.add('hidden');
    document.getElementById('schedule-view').classList.remove('hidden');
}