document.addEventListener("DOMContentLoaded", () => {
    const navMenu = document.querySelector("#navMenu");
    const navToggler = document.querySelector("[data-nav-toggle='collapse']");
    const dropdownToggles = Array.from(document.querySelectorAll("[data-nav-toggle='dropdown']"));

    const closeDropdowns = (exceptToggle = null) => {
        dropdownToggles.forEach((toggle) => {
            if (exceptToggle && toggle === exceptToggle) {
                return;
            }
            const menu = toggle.parentElement?.querySelector(".dropdown-menu");
            toggle.setAttribute("aria-expanded", "false");
            menu?.classList.remove("show");
        });
    };

    if (navToggler && navMenu) {
        navToggler.addEventListener("click", () => {
            const isOpen = navMenu.classList.contains("show");
            navMenu.classList.toggle("show", !isOpen);
            navToggler.setAttribute("aria-expanded", String(!isOpen));
            if (isOpen) {
                closeDropdowns();
            }
        });
    }

    dropdownToggles.forEach((toggle) => {
        toggle.addEventListener("click", (event) => {
            event.preventDefault();
            const menu = toggle.parentElement?.querySelector(".dropdown-menu");
            if (!menu) {
                return;
            }
            const isOpen = menu.classList.contains("show");
            closeDropdowns(toggle);
            toggle.setAttribute("aria-expanded", String(!isOpen));
            menu.classList.toggle("show", !isOpen);
        });
    });

    document.addEventListener("click", (event) => {
        const insideDropdown = event.target instanceof Element
            ? event.target.closest(".nav-item.dropdown")
            : null;
        if (!insideDropdown) {
            closeDropdowns();
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeDropdowns();
            if (navMenu && window.innerWidth < 992) {
                navMenu.classList.remove("show");
                navToggler?.setAttribute("aria-expanded", "false");
            }
        }
    });
});
