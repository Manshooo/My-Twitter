'use strict'

window.addEventListener('DOMContentLoaded', function() {
	setMinHeight();
	document.addEventListener("click", function(event) {
		let dropdown_menu_target = event.target.parentNode.querySelector('.dropdown-menu');
		if (event.target.closest(".auth-account > #account")) return;
		switch (event.target.getAttribute("data-target")) {
			case "dropdown_menu":
				event.preventDefault();
				dropdown_menu_target.classList.toggle("dropdown-menu-open");
				break;
			default:
				document.querySelector(".dropdown-menu").classList.remove("dropdown-menu-open")
		}
	});
});

function setMinHeight() {
	let headerHeight = Number(document.querySelector("header").offsetHeight);
	let navHeight = Number(document.querySelector("nav").offsetHeight);
	let footerHeight = Number(document.querySelector("footer").offsetHeight);
	let minHeight = window.innerHeight-(headerHeight+footerHeight+navHeight+10);
	document.querySelector(".content").style.minHeight = minHeight + 'px';
}
