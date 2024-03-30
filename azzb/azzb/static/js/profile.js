"use strict";
$(document).ready(function () {
	let action_buttons = $(".wrapper-form-actions");
	$('#submit[name=post]').click(function (e) {
		e.preventDefault();
		const csrftoken = getCookie('csrftoken');
		let data = {
			"text": $("#id__post-text").text(),
		}
		$("#id__post-text").text("");
		$.ajax({
			type: "POST",
			url: "/api/new-post/",
			contentType: "application/json; charset=utf-8",
			data: JSON.stringify(data),
			headers: { "X-CSRFToken": csrftoken },
			dataType: "html",
			beforeSend: loadingIndicator(),
			success: function (data) {
				loadingIndicator();
				$("#profile-feed").prepend(data);
				if ($(".no_post")) {
					$(".no_post").remove()
				}
			},
			error: function (data) {
				loadingIndicator();
				console.log(data);
			},
		});
	});
	function loadingIndicator() {
		let text = $("#id__post-text");
		if (text.hasClass("in-process")) {
			text.removeAttr("disabled");
			text.removeClass("in-process");
		} else {
			text.attr("disabled");
			text.addClass("in-process")
		}
	}
	document.addEventListener("click", function (e) {
		switch (e.target.getAttribute("name")) {
			case "new_post":
				return;
			case "form_actions":
				return;
			default:
				action_buttons.hide();
		}
	});
});

function showEditPost() {
	let action_buttons = $(".wrapper-form-actions");
	action_buttons.show();
}