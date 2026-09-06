/* Sort and filter the fiction / non-fiction index lists in place.
 *
 * The list is rendered once, by year, newest first. Without JavaScript that is
 * still a complete, correctly ordered list -- this only adds re-sorting and
 * filtering, and the controls stay hidden until it runs, so they are never dead.
 */
(function () {
  var list = document.querySelector(".work-list");
  var controls = document.querySelector(".list-controls");
  if (!list || !controls) return;

  var rows = Array.prototype.slice.call(list.querySelectorAll(".work-row"));
  var heads = Array.prototype.slice.call(list.querySelectorAll(".year-head"));
  if (!rows.length) return;

  var sortSel = controls.querySelector(".lc-sort");
  var langSel = controls.querySelector(".lc-lang");
  var tagSel = controls.querySelector(".lc-tag");
  var count = controls.querySelector(".lc-count");

  // Devanagari and Latin titles sort together sensibly under a Marathi collator;
  // fall back to the default if the browser has no data for it.
  var collator;
  try {
    collator = new Intl.Collator("mr", { sensitivity: "base", numeric: true });
  } catch (e) {
    collator = new Intl.Collator(undefined, { sensitivity: "base", numeric: true });
  }

  // Sort key is the link text, not a data attribute: the title is already in the
  // markup, and duplicating it costs 3 bytes per character in Devanagari.
  // Pandoc wraps long titles, so collapse the whitespace it introduces.
  function titleOf(row) {
    var a = row.querySelector("a");
    return a ? a.textContent.replace(/\s+/g, " ").trim() : "";
  }
  rows.forEach(function (r) { r.__key = titleOf(r); });

  var byYear = rows.slice();          // the server-rendered order
  var byTitle = rows.slice().sort(function (a, b) {
    return collator.compare(a.__key, b.__key);
  });

  function matches(row) {
    var lang = langSel ? langSel.value : "";
    var tag = tagSel ? tagSel.value : "";
    if (lang && row.dataset.lang !== lang) return false;
    if (tag) {
      var tags = (row.dataset.tags || "").split(",");
      if (tags.indexOf(tag) === -1) return false;
    }
    return true;
  }

  function render() {
    var byTitleMode = sortSel.value === "title";
    var order = byTitleMode ? byTitle : byYear;

    var shown = 0;
    var frag = document.createDocumentFragment();
    var lastYear = null;

    order.forEach(function (row) {
      if (!matches(row)) return;
      shown++;
      // Year separators belong to the chronological view only, and only where
      // the year still has a visible row after filtering.
      if (!byTitleMode && row.dataset.year && row.dataset.year !== lastYear) {
        lastYear = row.dataset.year;
        var head = heads.filter(function (h) { return h.dataset.year === lastYear; })[0];
        if (head) frag.appendChild(head);
      }
      frag.appendChild(row);
    });

    heads.forEach(function (h) { if (!frag.contains(h)) h.remove(); });
    rows.forEach(function (r) { if (!frag.contains(r)) r.remove(); });
    list.appendChild(frag);

    count.textContent = shown === rows.length
      ? shown + " works"
      : shown + " of " + rows.length + " works";
  }

  [sortSel, langSel, tagSel].forEach(function (el) {
    if (el) el.addEventListener("change", render);
  });

  // "By topic" links point at the site-wide tag pages so they work without
  // JavaScript. With JS, filter this page's list instead -- staying on Fiction
  // when you click "Sci-Fi" is what a reader means. Clicking the active topic
  // again clears it.
  if (tagSel) {
    document.querySelectorAll(".topic-link").forEach(function (a) {
      a.addEventListener("click", function (ev) {
        var t = a.dataset.topic;
        if (!t) return;
        ev.preventDefault();
        tagSel.value = tagSel.value === t ? "" : t;
        syncTopicLinks();
        render();
      });
    });
  }

  function syncTopicLinks() {
    var active = tagSel ? tagSel.value : "";
    document.querySelectorAll(".topic-link").forEach(function (a) {
      a.classList.toggle("is-active", a.dataset.topic === active && active !== "");
    });
  }

  if (tagSel) tagSel.addEventListener("change", syncTopicLinks);

  controls.hidden = false;
  render();
})();
