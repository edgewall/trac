body {
	background: #fff;
	margin: 10px;
	padding: 0;
	color: #000;
	font: normal 100% 'Bitstream Vera Sans', Verdana, Helvetica, Arial, sans-serif;
}
hr,.hide { display: none; }
a:link, a:visited, a.noline,b.tl-item-link {
	text-decoration: none;
	color: #b00;
	border-bottom: 1px dotted #bbb;
}
a:hover {
	color: #b00;
	background: #f7f7f7;
}
a.noline { border-bottom: none; }
address { font-style: normal; }
img { border: none; }
#browser-rev, #log-hdr,#log-hdr,#timeline-hdr,#chg-hdr,#report-hdr,#tkt-hdr {
	font-size: 110%;
	margin-right: 1em;
        margin-top: .5em;
}

/* Forms */

input, textarea, select {
	border: 1px solid #ccc;
	background: #fff;
}
input[type="submit"], input[type="reset"] { background: #eee; }
input[type="submit"]:hover, input[type="reset"]:hover { background: #ccb; }
option {  border-bottom: 1px solid #ccc; }

/* Header */

#header { }
#hdrlogo,#hdrlogo img,#hdrlogo:hover {
	background: transparent;
	margin-bottom: -1em;
}
#header-links, #subheader-links, #navbar {
	font: normal 11px Verdana, 'Bitstream Vera Sans', Helvetica, Arial, sans-serif;
	color: #000;
}
#header-links, #subheader-links {
	padding: 2px 0em;
	text-align: right;
}
#subheader-links a,#header-links a { padding: 0 .5em; }
.subheader-sublinks { 
 background: #f7f7f7;
 border: 1px solid #ccc;
 color: #888;
 padding: 0 .5em;
 text-align: left;
}

/* Footer */

#footer {
	font-size: 75%;
	color: #bbb;
	border-top: 1px solid;
	padding: .5em 0;
}
#footer a { color: #bbb; }
#footer-left {
	float: left;
	padding: 0 1em;
	border-left: 1px dashed;
	border-right: 1px dashed;
}
#footer-right { text-align: right; }
#footer-logo {
	float: left;
	margin-right: 1em;
	margin-top: .3em;
}

/* Navbar  */

#navbar {
	clear: both;
	border: 1px solid #999;
	background: #eee;
	margin: .15em 0;
	min-width: 500px;          
        height: 16px;
}
#navbar-links { float: right; }
a.navbar-link, a.navbar-link-active,a.navbar-link-active:hover {
	display: block;
	float: left;
	border-left: 1px solid #999;
	border-bottom: none;
	margin: 0;
        height: 14px;
	padding: .1em 1.5em;
	color: #000;
	background: url(<?cs var:$htdocs_location ?>dots.gif) top left no-repeat;
}
a.navbar-link-active {
	background: #ccc;
	font-weight: bold;
}
a.navbar-link:hover { background-color: #ccb; }
#page-content { clear: none; }

/* Wiki */

#wiki-history {
	visibility: hidden;
	background: #f7f7f0;
	border: 1px solid #999;
	font-size: 75%;
	position: absolute;
	display: inline;
	margin: 10px;
	right:10px;
	border-collapse: separate;
	border-spacing: 0;
	padding: .5em;
}
a.wiki-history-link {
	display: block;
	border: none;
}
a.wiki-history-link:hover,tr.wiki-history-row:hover {
	background: #ccb;
	color: #b00;
}
a.wiki-missing-page:link
{
	color: #998;
	background: #fafaf0;
}
a.wiki-missing-page:hover { color: #000; }
#wiki-body {
	line-height: 140%;
	margin: 1em;
}

#browser-list,#common-list {
	margin: .5em 0 2em 0;
	border-bottom: 1px solid #eee;
	border-collapse: collapse;
	line-height: 130%;
}
#browser-list td { 
padding: 0 .25em; 
	border: 1px dotted #ddd;

}

#browser-list { width: 100%; }
tr.br-row-even, tr.br-row-odd,tr.row-even, tr.row-odd { border-top: 1px solid #ddd; }
tr.br-row-even,tr.row-even { background-color: #fff; }
tr.br-row-odd,tr.row-odd { background-color: #f7f7f7; }
tr.br-row-even:hover,tr.br-row-odd:hover { background: #eed; }

<?cs if:trac.active_module == 'report'?>
td.summary-col { border-left: 1px dotted #ccc; }
td.report-col { width: 1px; }
<?cs /if ?>


<?cs if:trac.active_module == 'browser' ?>
/* Browser */
#browser-chgrev {
	display: inline;
	margin: 0;
	float: right;
	font-size: 9px;
	width: 15em;
	text-align: right;
}
#browser-chgrev input { text-align: center; }
#browser-pathlinks {
	padding-bottom: .5em;
	border-bottom: 1px solid #ccc;
}
tr.browser-listhdr { border-bottom: 1px solid #eee; }
tr.browser-listhdr th {
	text-align: left;
	padding: 0 1em 0 0;
	font-size: 13px;
}
#browser-list a.block-link { 
	display: block;
	border-bottom: none;
	background: transparent;
}
#browser-list td { padding: 0 .5em; }
th { text-align: left; }
td.br-size-col,td.br-rev-col,td.br-date-col,td.br-summary-col,td.br-chg-col { border-left: 1px solid #eee; }
td.br-icon-col { }
td.br-rev-col, td.br-chg-col { text-align: center; }
td.br-rev-col a { font-weight: bold; }
td.br-name-col { width: 100%; }
td.br-size-col, td.br-rev-col, td.br-date-col {
	color: #888;
	white-space: nowrap;
}
td.br-icon-col, td.br-report-col, td.br-ticket-col { width: 1em; }
<?cs /if ?>


/* Log */


<?cs if:trac.active_module == 'timeline' ?>
/* Timeline */
#timeline-prefs {
	background: #f7f7f0;
	border: 1px solid #d7d7d7;
	float: right;
	font-size: 9px;
	padding: .5em;
	margin-left: 1em;
	margin-bottom: 1em;
}
#timeline-prefs-checks { }
#timeline-prefs-btns {
	text-align: right;
	margin-top: 1em;
}
.timeline-daysep {
	font-size: 105%;
	border-bottom: 1px solid #d7d7d7;
}
.tl-day { 
	line-height: 130%; 
	margin-left: 1em;
}
a.tl-item { 
	display: block;
	color: #000;
	padding: 1px 0;
	margin: 1px; 
	border: none; 
}
a.tl-item:hover {
	background-color: #eed;
	color: #000;
}
.tl-item-time { color: #777; }
.tl-item-link { font-weight: normal; }
.tl-item-msg { }
.tl-item-descr {
	display: block;
	margin-left: 6.5em;
	font-size: 80%;
}
.tl-item-icon { 
	vertical-align: text-top; 
	margin: 0;
}
<?cs /if ?>

<?cs if:trac.active_module == 'changeset' ?>
/* Changeset */
.chg-name {
	display: block;
	float: left;
	width: 8em;
	text-align: right;
	margin-right: .5em;
}
.chg-val { }
ul.chg-list {
	padding: .5em;
	margin-left: 8em;
	list-style: none;
}
.chg-file-comment {
	display: none;
	color: #bbb;
	margin-left: .5em;
	font-size: 75%;
}
.chg-file-add,.chg-file-mod,.chg-file-rem,.diff-legend-unmod,.diff-legend-mod,.diff-legend-add,.diff-legend-rem {
	display: block;
	float: left;
	width: 1em;
	height: 1em;
	margin-right: .5em;
	border: 1px solid #999;
}
#chg-diff { 
	border-top: 1px solid #d7d7d7;
	margin-bottom: 3em;
}
#chg-legend { }
table.diff-table { 
	border: 1px solid #d7d7d7; 
	border-left: 1px solid #999; 
	border-right: 1px solid #fff; 
	border-bottom: 1px solid #fff; 
	width: 100%;
	font-size: 12px;
	border-collapse: collapse;
	margin-left: 1px;
}
.chg-diff-file { 
	background: #eee;
	padding: 5px;
	padding-top: 0;
	margin-top: 2em;
	border: 1px solid #d7d7d7; 
}
.chg-diff-hdr { 
	font-size: 11px;
	color: #666; 
	padding: 2px .25em;
	border-bottom: 1px solid #999; 
	margin: 0;
	margin-bottom: 1px;
}
table.diff-table td { 
	border-left: dashed 1px #d7d7d7;
	padding: 0 .5em;
	font-family: monospace;
	vertical-align: top;
	margin-top: 1em;
}
td.diff-line { 
	background: #eed;
	border: 1px solid #d7d7d7;
	border-top: 1px solid #fff;
	border-bottom: 1px solid #998;
	font-weight: bold;
	font-size: 11px;
}
.diff-modified,.chg-file-mod,.diff-legend-mod { background-color: #fd8; }
.diff-unmodified, .diff-legend-unmod { background-color: #fff }
.diff-remove-left,.chg-file-rem,.diff-legend-rem { background-color: #f88; }
.diff-remove-right { background-color: #ffaaaa; }
.diff-add-left,.chg-file-add { background-color: #dfd; }
.diff-add-right, .diff-legend-add { background-color: #cfc; }
<?cs /if ?>

<?cs if:trac.active_module == 'ticket' ?>
/* Ticket */

#tkt-ticket,#tkt-changes { 
	background: #ffd;
	border: 1px solid #dd9;
	border-width: 1px 3px 3px 1px;
	padding: .5em;
	max-width: 700px;
}
#tkt-left { 
	width: 50%;
	float: left;
	border-right: 1px solid #dd9;
	padding: .5em;
}
#tkt-right { 
	padding: .5em;
}
#tkt-date { 
	float: right;
	font-size: 75%;
	color: #996; 
}
.tkt-prop { 
	border-bottom: 1px dotted #eed;
}
.tkt-label { 
	color: #996; 
	font-weight: normal;
	padding: 0 .5em;
	float: left;
	width: 8em;
}
.tkt-val { }
#tkt-summary { 
	margin: 0;
	font-size: 100%;
	border-bottom: 1px solid #dd9;
	padding-bottom: .25em;
}
#tkt-descr { 
	border-top: 1px solid #dd9;
	padding-top: .5em;
}
#tkt-left,#tkt-right { 
	font-size: 80%;
}
#tkt-changes-hdr { 
	font-size: 110%;
	margin-bottom: .5em;
	margin-top: 1em;
}
#tkt-changes { 
	border-color: #d7d7d7;
	background: #fff;
	font-size: 80%;
	padding: 0 .5em;
	padding-left: 1.5em;
}
.tkt-chg-mod { 
	color: #999;
	border-bottom: 1px solid;
	margin-top: .5em;
	margin-left: -1em;
	font-size: 100%;
	font-weight: normal;
	padding: 0 .5em;
}
ul.tkt-chg-list { 
	padding: 0 1em;
	list-style: square;
}
li.tkt-chg-change { margin: 0 }
.tkt-chg-comment-hdr { 
	margin: 0;
	font-size: 100%;
}
.tkt-chg-comment p { margin: .25em }
.tkt-chg-comment { 
	margin: 0;
	margin-left: 1em;
}
<?cs /if ?>


<?cs if:trac.active_module == 'about' ?>
<?cs /if ?>