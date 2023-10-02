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
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            // Does this cookie string begin with the name we want?
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}
/* 
$.ajax({
	type: 'GET',
	url: '/posts-json/',
	success: function(response){
		console.log(response)
	},
	error: function(error){
		console.log(error)
	}
})
 */