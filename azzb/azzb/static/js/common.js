'use strict'
const csrftoken = getCookie('csrftoken');
window.addEventListener('DOMContentLoaded', function () {
	document.addEventListener("click", function (event) {
		let dropdown_menu_target = event.target.parentNode.querySelector('.dropdown-menu');
		console.log(event.target)
		/* if (event.target.closest(".auth-account > #account")) return; */
		switch (event.target.closest(".dropdown") !== null) {
			case true:
				event.preventDefault();
				dropdown_menu_target.classList.toggle("dropdown-menu-open");
				break;
			default:
				document.querySelector(".dropdown-menu").classList.remove("dropdown-menu-open")
		}
	});
});

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
/* function log_out(e) {
	e.preventDefault()
	$.ajax({
		type: "POST",
		url: "/auth/logout/",
		headers: {"X-CSRFToken": csrftoken },
		data: "",
		dataType: "html",
		success: function (response) {
			console.log(response);
			window.location = response;
		}
	});
} */
function post_like(event) {
	let post = event.target.closest(".post")
	let id = post.dataset.postid
	let data = {
		"id": id,
	}
	$.ajax({
		type: "POST",
		url: "/api/like-post/",
		contentType: "application/json; charset=utf-8",
		headers: { "X-CSRFToken": csrftoken },
		data: JSON.stringify(data),
		dataType: "json",
		success: function (response) {
			$(post).find('.like__count').text(response.likes_count);
			if (response.liked) {
				$(post).find('.post__like').addClass("liked")
			} else {
				$(post).find('.post__like').removeClass("liked")
			}

		},
		error: function (response) {
		}
	});
}
let isAnimating = false
const copyToClipboard = async (copyData) => {
	const showTooltip = (text) => { $('.tooltip', () => { isAnimating = true }).text(text).fadeIn(250).delay(500).fadeOut(250, () => { isAnimating = false }); }
	try {
		if (isAnimating) return;
		const decodedUrl = decodeURIComponent(copyData);
		await navigator.clipboard.writeText(decodedUrl);
		showTooltip("Скопировано!")
	} catch (error) {
		showTooltip("Ошибка!")
	}
}