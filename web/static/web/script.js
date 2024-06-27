function setParam(name, value) {
  var l = window.location;

  /* build params */
  var params = {};
  var x = /(?:\??)([^=&?]+)=?([^&?]*)/g;
  var s = l.search;
  for(var r = x.exec(s); r; r = x.exec(s))
  {
    r[1] = decodeURIComponent(r[1]);
    if (!r[2]) r[2] = '%%';
    params[r[1]] = r[2];
  }

  /* set param */
  params[name] = encodeURIComponent(value);

  /* build search */
  var search = [];
  for(var i in params)
  {
    var p = encodeURIComponent(i);
    var v = params[i];
    if (v != '%%') p += '=' + v;
    search.push(p);
  }
  search = search.join('&');

  /* execute search */
  l.search = search;
}

var coll = document.getElementsByClassName("collapsible");
var i;

for (i = 0; i < coll.length; i++) {
  coll[i].addEventListener("click", function() {
    this.classList.toggle("active");
    var content = this.nextElementSibling;
    if (content.style.display === "block") {
      content.style.display = "none";
    } else {
      content.style.display = "block";
    }
  });
}
