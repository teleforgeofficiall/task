function initScrollReveal() {
  if (!('IntersectionObserver' in window)) return;

  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.style.animationPlayState = 'running';
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1, rootMargin: '0px 0px -50px 0px' });

  document.querySelectorAll('.animate-in').forEach(el => {
    el.style.animationPlayState = 'paused';
    observer.observe(el);
  });
}

function animateCounter(element, target, duration) {
  if (!element) return;
  const start = 0;
  const startTime = performance.now();

  function update(currentTime) {
    const elapsed = currentTime - startTime;
    const progress = Math.min(elapsed / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    const current = Math.floor(start + (target - start) * eased);
    element.textContent = formatCurrency(current);
    if (progress < 1) {
      requestAnimationFrame(update);
    } else {
      element.textContent = formatCurrency(target);
    }
  }
  requestAnimationFrame(update);
}

// Tab page transition
document.addEventListener('DOMContentLoaded', () => {
  initScrollReveal();
});

// Re-init scroll reveal when navigating tabs
const _origNavigateTab = navigateTab;
navigateTab = function(name) {
  _origNavigateTab(name);
  setTimeout(initScrollReveal, 100);
};

// Handle leaderboard tab to stop interval when leaving
const _origLoadTab = loadTab;
loadTab = function(name) {
  if (name !== 'Top' && _leaderboardInterval) {
    clearInterval(_leaderboardInterval);
    _leaderboardInterval = null;
  }
  _origLoadTab(name);
};
