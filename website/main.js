let whitemode, mdRenderedAlready;


document.addEventListener('DOMContentLoaded', initialize);

async function initialize(){
    whiteMode();
    initMD();
    initSections();
}

// ======================== Section tiles ========================
// The subject sections become a row of tiles (side by side, like the course buttons). Clicking a
// tile shows that section's courses under the tiles; clicking it again hides them. One section is
// shown at a time, and the last one is remembered per viewer (when storage is available).

function initSections(){
    const sections = [];
    document.querySelectorAll('.container').forEach((container) => {
        const h2 = container.querySelector(':scope > h2');
        if (h2 && container.querySelector('.pdf-button-container')) sections.push({container, title: h2.textContent.trim()});
    });
    if (!sections.length) return;

    const nav = document.createElement('div');
    nav.className = 'container section-nav';
    const tiles = document.createElement('div');
    tiles.className = 'section-tiles';
    nav.appendChild(tiles);
    sections[0].container.before(nav);

    let current = null;
    try { current = localStorage.getItem('openSection'); } catch (e) {}

    const show = (title) => {
        current = title;
        for (const s of sections) {
            const on = s.title === title;
            s.container.hidden = !on;
            s.tile.classList.toggle('active', on);
            s.tile.setAttribute('aria-expanded', on);
        }
        try { title ? localStorage.setItem('openSection', title) : localStorage.removeItem('openSection'); } catch (e) {}
    };

    for (const s of sections) {
        const tile = document.createElement('button');
        tile.type = 'button';
        tile.className = 'section-tile';
        tile.textContent = s.title;
        tile.addEventListener('click', () => show(current === s.title ? null : s.title));
        tiles.appendChild(tile);
        s.tile = tile;
        s.container.classList.add('section-panel');
    }
    show(sections.some((s) => s.title === current) ? current : null);
}

// ======================== MARKDOWN RENDERER ========================

function reloadMD(){
    const mdRender = document.getElementById('md-render');

    mdRenderedAlready = JSON.parse(sessionStorage.getItem("renderedMD"));
    if (mdRenderedAlready){
        mdRender.render();
    }
}

function initMD(){
    sessionStorage.setItem('renderedMD', false);
    addEventListener('zero-md-ready', (e) => {
        e.target.render();
        sessionStorage.setItem('renderedMD', true);
    });
}

// ======================== White Mode ========================

function whiteModeToggle(){
    whitemode = JSON.parse(localStorage.getItem('whitemode'));
    document.body.classList.toggle('whitemode');
    localStorage.setItem('whitemode', !whitemode);
}

function whiteMode(){
    const themeSwitch = document.getElementById('theme-switch');

    whitemode = localStorage.getItem('whitemode');
    if (whitemode == null) localStorage.setItem('whitemode', false);
    whitemode = JSON.parse(localStorage.getItem('whitemode'));

    if (whitemode) document.body.classList.toggle('whitemode');

    themeSwitch.addEventListener("click", () => {
        whiteModeToggle();
        reloadMD();
    });
}

// ======================== Popups buttons ========================

function openPopup(popupId) {
    document.getElementById(popupId).style.display = "flex";
}

function closePopup(event, popupId) {
    if (!event || event.target === document.getElementById(popupId)) {
        document.getElementById(popupId).style.display = "none";
    }
}