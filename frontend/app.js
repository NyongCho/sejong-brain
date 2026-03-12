/**
 * SejongBrain — 프론트엔드 인터랙션
 * API 통신, 검색이벤트, 공유 기능
 */

const API_BASE = window.location.origin;

// ─── DOM 요소 ────────────────────────────────
const searchForm = document.getElementById('searchForm');
const questionInput = document.getElementById('questionInput');
const submitBtn = document.getElementById('submitBtn');
const suggestions = document.getElementById('suggestions');
const suggestionChips = document.getElementById('suggestionChips');
const loading = document.getElementById('loading');
const answerContainer = document.getElementById('answerContainer');
const answerText = document.getElementById('answerText');
const sourcesSection = document.getElementById('sourcesSection');
const sourcesList = document.getElementById('sourcesList');
const shareBtn = document.getElementById('shareBtn');
const feedbackGood = document.getElementById('feedbackGood');
const feedbackBad = document.getElementById('feedbackBad');

// 현재 결과 저장 (공유용)
let currentResult = null;

// ─── 초기화 ──────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    loadSuggestions();
});

// ─── 추천 질문 로드 ──────────────────────────
async function loadSuggestions() {
    try {
        const resp = await fetch(`${API_BASE}/api/suggestions`);
        if (!resp.ok) throw new Error('suggestions fetch failed');
        const data = await resp.json();

        suggestionChips.innerHTML = '';
        data.suggestions.forEach(s => {
            const chip = document.createElement('button');
            chip.className = 'suggestion-chip';
            chip.textContent = s.text;
            chip.addEventListener('click', () => {
                questionInput.value = s.text;
                handleSearch(s.text);
            });
            suggestionChips.appendChild(chip);
        });
    } catch (e) {
        // 폴백: 하드코딩 추천 질문
        const fallback = [
            '수강신청은 최대 몇 학점까지?',
            '장학금 기본이수학점은?',
            '성적 우수자 초과 학점 신청',
        ];
        suggestionChips.innerHTML = '';
        fallback.forEach(text => {
            const chip = document.createElement('button');
            chip.className = 'suggestion-chip';
            chip.textContent = text;
            chip.addEventListener('click', () => {
                questionInput.value = text;
                handleSearch(text);
            });
            suggestionChips.appendChild(chip);
        });
    }
}

// ─── 검색 폼 제출 ────────────────────────────
searchForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const question = questionInput.value.trim();
    if (question) {
        handleSearch(question);
    }
});

// ─── 검색 처리 메인 함수 ─────────────────────
async function handleSearch(question) {
    // UI 상태: 로딩
    showLoading();
    hideAnswer();
    suggestions.style.display = 'none';

    try {
        const resp = await fetch(`${API_BASE}/api/ask`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question }),
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || `서버 오류 (${resp.status})`);
        }

        const data = await resp.json();
        currentResult = data;

        // UI 상태: 답변 표시
        hideLoading();
        showAnswer(data);

    } catch (e) {
        hideLoading();
        showError(e.message);
    }
}

// ─── UI 헬퍼 함수 ────────────────────────────
function showLoading() {
    loading.style.display = 'block';
}

function hideLoading() {
    loading.style.display = 'none';
}

function showAnswer(data) {
    answerContainer.style.display = 'block';

    if (window.marked) {
        answerText.innerHTML = marked.parse(data.answer);
    } else {
        answerText.textContent = data.answer;
    }

    // 출처 표시
    if (data.sources && data.sources.length > 0) {
        sourcesSection.style.display = 'block';
        sourcesList.innerHTML = '';

        data.sources.forEach(source => {
            const card = document.createElement('div');
            card.className = 'source-card';

            let label = source.title || '문서';
            if (source.page) label += ` (p.${source.page})`;

            card.innerHTML = `<span class="source-icon">📄</span><span>${label}</span>`;
            sourcesList.appendChild(card);
        });
    } else {
        sourcesSection.style.display = 'none';
    }

    // 피드백 버튼 초기화
    feedbackGood.classList.remove('active');
    feedbackBad.classList.remove('active');
}

function hideAnswer() {
    answerContainer.style.display = 'none';
}

function showError(message) {
    answerContainer.style.display = 'block';
    answerText.textContent = `⚠️ 오류: ${message}\n\n잠시 후 다시 시도해주세요.`;
    sourcesSection.style.display = 'none';
}

// ─── 공유 기능 ───────────────────────────────
shareBtn.addEventListener('click', () => {
    if (!currentResult) return;

    const shareText = `🎓 세종대 AI 학사 도우미에게 물어봤더니!\n\nQ: ${currentResult.question}\nA: ${currentResult.answer.substring(0, 150)}...\n\n👉 나도 물어보기: ${window.location.href}\n#세종대 #학사정보 #SejongBrain`;

    navigator.clipboard.writeText(shareText).then(() => {
        showToast('📋 공유 텍스트가 클립보드에 복사되었습니다!');
    }).catch(() => {
        // 폴백: textarea 복사
        const textarea = document.createElement('textarea');
        textarea.value = shareText;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        showToast('📋 공유 텍스트가 클립보드에 복사되었습니다!');
    });
});

// ─── 피드백 버튼 ─────────────────────────────
feedbackGood.addEventListener('click', () => {
    feedbackGood.classList.toggle('active');
    feedbackBad.classList.remove('active');
    showToast('👍 피드백 감사합니다!');
    // TODO: 피드백 데이터를 서버에 전송
});

feedbackBad.addEventListener('click', () => {
    feedbackBad.classList.toggle('active');
    feedbackGood.classList.remove('active');
    showToast('감사합니다. 답변 품질 개선에 반영하겠습니다.');
    // TODO: 피드백 데이터를 서버에 전송
});

// ─── Toast 알림 ──────────────────────────────
function showToast(message) {
    // 기존 토스트 제거
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    document.body.appendChild(toast);

    requestAnimationFrame(() => {
        toast.classList.add('show');
    });

    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 2500);
}
