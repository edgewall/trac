function view_history() {
        var history = document.getElementById("wiki-history");
        if (history) {
                if (history.style.visibility != "visible") {
                        history.style.visibility = "visible";
                }
                else {
                        history.style.visibility = "hidden";
                }
        }
}

// A better way than for example hardcoding foo.onload
function addEvent(obj, evType, fn){
 if (obj.addEventListener){
    obj.addEventListener(evType, fn, true);
    return true;
 } else if (obj.attachEvent){
    var r = obj.attachEvent("on"+evType, fn);
    return r;
 } else {
    return false;
 }
} 

// From http://www.kryogenix.org/code/browser/searchhi/ 
function highlightWord(node,word,searchwordindex) {
	// Iterate into this nodes childNodes
	if (node.hasChildNodes) {
		var hi_cn;
		for (hi_cn=0;hi_cn<node.childNodes.length;hi_cn++) {
			highlightWord(node.childNodes[hi_cn],word,searchwordindex);
		}
	}
	
	// And do this node itself
	if (node.nodeType == 3) { // text node
		tempNodeVal = node.nodeValue.toLowerCase();
		tempWordVal = word.toLowerCase();
		if (tempNodeVal.indexOf(tempWordVal) != -1) {
			pn = node.parentNode;
			if (pn.className.substring(0,10) != "searchword") {
				// word has not already been highlighted!
				nv = node.nodeValue;
				ni = tempNodeVal.indexOf(tempWordVal);
				// Create a load of replacement nodes
				before = document.createTextNode(nv.substr(0,ni));
				docWordVal = nv.substr(ni,word.length);
				after = document.createTextNode(nv.substr(ni+word.length));
				hiwordtext = document.createTextNode(docWordVal);
				hiword = document.createElement("span");
				hiword.className = "searchword"+(searchwordindex % 5);
				hiword.appendChild(hiwordtext);
				pn.insertBefore(before,node);
				pn.insertBefore(hiword,node);
				pn.insertBefore(after,node);
				pn.removeChild(node);
			}
		}
	}
}

function searchHighlight() {
	if (!document.createElement) return;
	ref = document.URL;
        if (ref.indexOf('/search/?q') == -1) ref = document.referrer;
	if (ref.indexOf('?') == -1) return;
	qs = ref.substr(ref.indexOf('?')+1);
	qsa = qs.split('&');
	for (i=0;i<qsa.length;i++) {
		qsip = qsa[i].split('=');
	        if (qsip.length == 1) continue;
        	if (qsip[0] == 'q' || qsip[0] == 'p') { // q= for Google, p= for Yahoo
			words = unescape(qsip[1].replace(/\+/g,' ')).split(/\s+/);
	                for (w=0;w<words.length;w++) {
				highlightWord(document.getElementById("searchable"),words[w],w);
                	}
	        }
	}
}

// Allow search highlighting of all pages
addEvent(window, 'load', searchHighlight);


addEvent(window, 'load', function() {
 var input, textarea;
 var inputs = document.getElementsByTagName('input');
 for (var i = 0; (input = inputs[i]); i++) {
   addEvent(input, 'focus', oninputfocus);
   addEvent(input, 'blur', oninputblur);
 }
 var textareas = document.getElementsByTagName('textarea');
 for (var i = 0; (textarea = textareas[i]); i++) {
   addEvent(textarea, 'focus', oninputfocus);
   addEvent(textarea, 'blur', oninputblur);
 }
});
function oninputfocus(e) {
 if (typeof e == 'undefined') {
   var e = window.event;
 }
 var source;
 if (typeof e.target != 'undefined') {
    source = e.target;
 } else if (typeof e.srcElement != 'undefined') {
    source = e.srcElement;
 } else { return; }
 source.style.border='1px solid #886';
}
function oninputblur(e) {
 if (typeof e == 'undefined') { var e = window.event; }
 var source;
 if (typeof e.target != 'undefined') {
    source = e.target;
 } else if (typeof e.srcElement != 'undefined') {
    source = e.srcElement;
 } else { return; }
 source.style.border='1px solid #d7d7d7';
}


