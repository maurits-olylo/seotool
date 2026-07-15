const storyCards = [...document.querySelectorAll(".landing-story-card")];

function activateStory(card) {
  const index = Number(card.dataset.index);
  storyCards.forEach((item) => item.classList.toggle("is-active", item === card));
  document.querySelector("#landing-step").textContent = `${String(index + 1).padStart(2, "0")} / ${String(storyCards.length).padStart(2, "0")}`;
  document.querySelector("#landing-title").textContent = card.dataset.title;
  document.querySelector("#landing-description").textContent = card.dataset.description;
  document.querySelector("#landing-action").childNodes[0].textContent = `${card.dataset.action} `;
  document.querySelector("#landing-progress").style.width = `${((index + 1) / storyCards.length) * 100}%`;
}

if (storyCards.length && "IntersectionObserver" in window && !window.matchMedia("(max-width: 960px)").matches) {
  const observer = new IntersectionObserver((entries) => {
    const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
    if (visible) activateStory(visible.target);
  }, {rootMargin: "-20% 0px -30% 0px", threshold: [.25, .5, .75]});
  storyCards.forEach((card) => observer.observe(card));
}
