function view_history() {
	var history = document.getElementById("history");
        if (history) {
		if (history.style.visibility != "visible") {
			history.style.visibility = "visible";
		}
		else {
			history.style.visibility = "hidden";
		}
        }
}
