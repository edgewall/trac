// A better way than for example hardcoding foo.onload
function addEvent(element, type, func){
  if (element.addEventListener) {
    element.addEventListener(type, func, true);
    return true;
  } else if (element.attachEvent) {
    return element.attachEvent("on" + type, func);
  }
  return false;
}

// Adapted from http://www.kryogenix.org/code/browser/searchhi/
function searchHighlight() {
  if (!document.createElement) return;

  var div = document.getElementById("searchable");
  if (!div) return;

  function getSearchWords(url) {
    if (url.indexOf('?') == -1) return [];
    var queryString = url.substr(url.indexOf('?') + 1);
    var params = queryString.split('&');
    for (var p in params) {
      var param = params[p].split('=');
      if (param.length < 2) continue;
      if (param[0] == 'q' || param[0] == 'p') { // q= for Google, p= for Yahoo
        return unescape(param[1].replace(/\+/g, ' ')).split(/\s+/);
      }
    }
    return [];
  }

  function highlightWord(node, word, searchwordindex) {
    // If this node is a text node and contains the search word, highlight it by
    // surrounding it with a span element
    if (node.nodeType == 3) { // Node.TEXT_NODE
      var pos = node.nodeValue.toLowerCase().indexOf(word.toLowerCase());
      if (pos >= 0 && !/^searchword\d$/.test(node.parentNode.className)) {
        var span = document.createElement("span");
        span.className = "searchword" + (searchwordindex % 5);
        span.appendChild(document.createTextNode(
            node.nodeValue.substr(pos, word.length)));
        var newNode = node.splitText(pos);
        newNode.nodeValue = newNode.nodeValue.substr(word.length);
        node.parentNode.insertBefore(span, newNode);
        return true;
      }
    } else if (!node.nodeName.match(/button|select|textarea/i)) {
      // Recurse into child nodes
      for (var i = 0; i < node.childNodes.length; i++) {
        if (highlightWord(node.childNodes[i], word, searchwordindex)) i++;
      }
    }
    return false;
  }

  var words = getSearchWords(document.URL);
  if (!words.length) words = getSearchWords(document.referrer);
  if (words.length) {
    for (var w in words) {
      if (words[w].length) highlightWord(div, words[w], w);
    }
  }
}


// Wiki editing stuff goes here
// Largely merged from Wikipedia (GPL) source
var noOverwrite=false;
var clientPC = navigator.userAgent.toLowerCase(); // Get client info
var is_gecko = ((clientPC.indexOf('gecko')!=-1) && (clientPC.indexOf('spoofer')==-1)
                && (clientPC.indexOf('khtml') == -1) && (clientPC.indexOf('netscape/7.0')==-1));
var is_safari = ((clientPC.indexOf('AppleWebKit')!=-1) && (clientPC.indexOf('spoofer')==-1));
var is_khtml = (navigator.vendor == 'KDE' || ( document.childNodes && !document.all && !navigator.taintEnabled ));
if (clientPC.indexOf('opera')!=-1) {
    var is_opera = true;
    var is_opera_preseven = (window.opera && !document.childNodes);
    var is_opera_seven = (window.opera && document.childNodes);
}

function escapeQuotes(text) {
    var re=new RegExp("'","g");
    text=text.replace(re,"\\'");
    re=new RegExp('"',"g");
    text=text.replace(re,'&quot;');
    re=new RegExp("\\n","g");
    text=text.replace(re,"\\n");
    return text;
}

function escapeQuotesHTML(text) {
    var re=new RegExp('"',"g");
    text=text.replace(re,"&quot;");
    return text;
}

function addInfobox(infoBox, infoText,text_alert) {
    alertText=text_alert;
    var clientPC = navigator.userAgent.toLowerCase(); // Get client info

    var re=new RegExp("\\\\n","g");
    alertText=alertText.replace(re,"\n");

    // if no support for changing selection, add a small copy & paste field
    // document.selection is an IE-only property. The full toolbar works in IE and
    // Gecko-based browsers.
    if(!document.selection && !is_gecko) {
         infoText=escapeQuotesHTML(infoText);
         document.write("<input size='40' class='wiki-infobox' id='"+infoBox+"' name='wiki_infobox' value=\""+
			infoText+"\" readonly='readonly' title='Sample Wiki markup' />");
     }
}

// this function generates the actual toolbar buttons with localized text
// we use it to avoid creating the toolbar where javascript is not enabled
function addButton(textArea, infoBox, imageFile, speedTip, tagOpen, tagClose, sampleText) {

    speedTip=escapeQuotes(speedTip);
    tagOpen=escapeQuotes(tagOpen);
    tagClose=escapeQuotes(tagClose);
    sampleText=escapeQuotes(sampleText);
    var mouseOver="";

    // we can't change the selection, so we show example texts
    // when moving the mouse instead, until the first button is clicked
    if(!document.selection && !is_gecko) {
        // filter backslashes so it can be shown in the infobox
        var re=new RegExp("\\\\n","g");
        tagOpen=tagOpen.replace(re,"");
        tagClose=tagClose.replace(re,"");
	mouseOver = "onMouseover=\"if(!noOverwrite){document.getElementById('"+infoBox+"').value='"+tagOpen+sampleText+tagClose+"'};\"";
    }
    document.write("<a tabindex='400' href=\"javascript:insertTags");
    document.write("('" + textArea +"','" + infoBox +"'");
    document.write(",'"+tagOpen+"','"+tagClose+"','"+sampleText+"');\">");
    document.write("<img width=\"24\" height=\"16\" src=\""+imageFile+"\" border=\"0\" ALT=\""+speedTip+"\" TITLE=\""+speedTip+"\""+mouseOver+" />");
    document.write("</a>");
    return;
}

// apply tagOpen/tagClose to selection in textarea,
// use sampleText instead of selection if there is none
// copied and adapted from phpBB
function insertTags(textArea, infoBox, tagOpen, tagClose, sampleText) {

//     var txtarea = textArea
    var txtarea = document.getElementById(textArea); 
    var infobox = document.getElementById(infoBox);
    // IE
    if(document.selection  && !is_gecko) {
        var theSelection = document.selection.createRange().text;
        if(!theSelection) { theSelection=sampleText;}
        txtarea.focus();
        if(theSelection.charAt(theSelection.length - 1) == " "){// exclude ending space char, if any
            theSelection = theSelection.substring(0, theSelection.length - 1);
            document.selection.createRange().text = tagOpen + theSelection + tagClose + " ";
        } else {
            document.selection.createRange().text = tagOpen + theSelection + tagClose;
        }

    // Mozilla
    } else if(txtarea.selectionStart || txtarea.selectionStart == '0') {
         var startPos = txtarea.selectionStart;
        var endPos = txtarea.selectionEnd;
        var scrollTop=txtarea.scrollTop;
        var myText = (txtarea.value).substring(startPos, endPos);
        if(!myText) { myText=sampleText;}
        if(myText.charAt(myText.length - 1) == " "){ // exclude ending space char, if any
            subst = tagOpen + myText.substring(0, (myText.length - 1)) + tagClose + " ";
        } else {
            subst = tagOpen + myText + tagClose;
        }
        txtarea.value = txtarea.value.substring(0, startPos) + subst +
          txtarea.value.substring(endPos, txtarea.value.length);
        txtarea.focus();

        var cPos=startPos+(tagOpen.length+myText.length+tagClose.length);
        txtarea.selectionStart=cPos;
        txtarea.selectionEnd=cPos;
        txtarea.scrollTop=scrollTop;

    // All others
    } else {
        var copy_alertText=alertText;
        var re1=new RegExp("\\$1","g");
        var re2=new RegExp("\\$2","g");
        copy_alertText=copy_alertText.replace(re1,sampleText);
        copy_alertText=copy_alertText.replace(re2,tagOpen+sampleText+tagClose);
        var text;
        if (sampleText) {
            text=prompt(copy_alertText);
        } else {
            text="";
        }
        if(!text) { text=sampleText;}
        text=tagOpen+text+tagClose;
        infobox.value=text;
        // in Safari this causes scrolling
        if(!is_safari) {
            txtarea.focus();
        }
        noOverwrite=true;
    }
    // reposition cursor if possible
    if (txtarea.createTextRange) txtarea.caretPos = document.selection.createRange().duplicate();
}
