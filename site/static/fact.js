(function () {
  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // Build indexes from DEMO_DATA
  var sentenceLookup = {};
  DEMO_DATA.turns.forEach(function (turn) {
    turn.sentences.forEach(function (s) {
      sentenceLookup[s.id] = {
        id: s.id,
        text: s.text,
        turnId: turn.id,
        speaker: turn.speaker,
        timestamp: turn.timestamp
      };
    });
  });

  var sentenceToFacts = {};
  var factToSentences = {};
  var factLookup = {};

  DEMO_DATA.facts.forEach(function (fact) {
    factLookup[fact.id] = fact;
    factToSentences[fact.id] = [];
    fact.quotes.forEach(function (q) {
      if (factToSentences[fact.id].indexOf(q.sentenceId) === -1) {
        factToSentences[fact.id].push(q.sentenceId);
      }
      if (!sentenceToFacts[q.sentenceId]) {
        sentenceToFacts[q.sentenceId] = [];
      }
      if (sentenceToFacts[q.sentenceId].indexOf(fact.id) === -1) {
        sentenceToFacts[q.sentenceId].push(fact.id);
      }
    });
  });

  // Render metadata and headers
  document.getElementById("doc-class-badge").textContent = DEMO_DATA.document.documentClass;
  document.getElementById("doc-subtitle").textContent =
    DEMO_DATA.document.title + " · " + DEMO_DATA.document.sourceDateLabel;

  var totalSentences = Object.keys(sentenceLookup).length;
  var citedSentenceCount = Object.keys(sentenceToFacts).length;
  document.getElementById("passage-counts").innerHTML =
    '<span class="badge badge-muted">' + DEMO_DATA.turns.length + " turns</span>" +
    '<span class="badge badge-blue">' + citedSentenceCount + " / " + totalSentences + " sentences cited</span>";

  var supersededCount = DEMO_DATA.facts.filter(function (f) { return f.status === "superseded"; }).length;
  var contradictedCount = DEMO_DATA.facts.filter(function (f) { return f.status === "contradicted"; }).length;
  document.getElementById("facts-count-badge").textContent = DEMO_DATA.facts.length + " facts";
  document.getElementById("facts-counts").innerHTML =
    (supersededCount ? '<span class="badge badge-blue">' + supersededCount + " superseded</span>" : "") +
    (contradictedCount ? '<span class="badge badge-warn">' + contradictedCount + " contradicted</span>" : "");

  document.getElementById("call-meta").innerHTML =
    "<span><strong>source_datetime:</strong> " + escapeHtml(DEMO_DATA.document.sourceDatetime) + "</span>" +
    "<span><strong>note:</strong> " + escapeHtml(DEMO_DATA.document.sampleNote) + " (a made-up sales call)</span>";

  // Render transcript turns
  var turnsList = document.getElementById("turns-list");
  turnsList.innerHTML = DEMO_DATA.turns.map(function (turn) {
    var sentencesHtml = turn.sentences.map(function (s) {
      var citing = sentenceToFacts[s.id];
      if (!citing || citing.length === 0) {
        return '<span class="sentence-plain" data-sentence-id="' + escapeHtml(s.id) + '">' + escapeHtml(s.text) + "</span>";
      }
      var badge = citing.length > 1
        ? '<span class="sentence-cite-count" aria-hidden="true">' + citing.length + "</span>"
        : "";
      return (
        '<span class="sentence-cited" role="button" tabindex="0" data-sentence-id="' + escapeHtml(s.id) +
        '" aria-label="Cited by ' + citing.length + (citing.length === 1 ? " fact" : " facts") + ": " + escapeHtml(s.text) + '">' +
        escapeHtml(s.text) + badge + "</span>"
      );
    }).join(" ");

    return (
      '<article class="turn-card" data-turn-id="' + escapeHtml(turn.id) + '" data-side="' + escapeHtml(turn.side) + '">' +
        '<div class="turn-head">' +
          '<div class="turn-speaker-wrap">' +
            '<span class="turn-speaker">' + escapeHtml(turn.speaker) + "</span>" +
            '<span class="turn-role">' + escapeHtml(turn.role) + "</span>" +
          "</div>" +
          '<span class="turn-time">' + escapeHtml(turn.timestamp) + "</span>" +
        "</div>" +
        '<p class="turn-text">' + sentencesHtml + "</p>" +
      "</article>"
    );
  }).join("");

  function statusBadgeClass(status) {
    if (status === "current") return "badge-ok";
    if (status === "superseded") return "badge-blue";
    if (status === "contradicted") return "badge-warn";
    if (status === "retracted") return "badge-err";
    return "badge-muted";
  }

  // Render facts
  var factsList = document.getElementById("facts-list");
  factsList.innerHTML = DEMO_DATA.facts.map(function (fact) {
    var cardClasses = ["fact-card"];
    if (fact.status === "superseded") cardClasses.push("is-superseded");
    if (fact.status === "contradicted") cardClasses.push("is-contradicted");

    var traitsHtml = fact.traits.map(function (t) {
      return '<span class="badge badge-purple">' + escapeHtml(t) + "</span>";
    }).join("");

    var classBadge = fact.factClass === "CustomerFact"
      ? '<span class="badge badge-blue">' + escapeHtml(fact.factClass) + "</span>"
      : '<span class="badge badge-teal">' + escapeHtml(fact.factClass) + "</span>";

    var relationHtml = "";
    if (fact.relation) {
      var relClass = fact.relation.type === "contradicted"
        ? "fact-relation fact-relation-contradicted"
        : "fact-relation fact-relation-superseded";
      relationHtml =
        '<div class="' + relClass + '">' +
          "<span>" + escapeHtml(fact.relation.label) + "</span>" +
        "</div>";
    }

    var quotesHtml = fact.quotes.map(function (q) {
      var src = sentenceLookup[q.sentenceId];
      var quoteText = src ? src.text : "";
      return (
        '<blockquote class="fact-quote">' +
          '<p class="fact-quote-text">"' + escapeHtml(quoteText) + '"</p>' +
          '<div class="fact-quote-meta">' +
            "<span>" + escapeHtml(q.speaker) + "</span>" +
            "<span>" + escapeHtml(q.timestamp) + "</span>" +
          "</div>" +
        "</blockquote>"
      );
    }).join("");

    var entitiesHtml = fact.entities.map(function (e) {
      return (
        '<span class="entity-chip">' +
          "<span>" + escapeHtml(e.name) + "</span>" +
          '<span class="entity-chip-kind">' + escapeHtml(e.kind) + "</span>" +
          '<span class="entity-chip-role">' + escapeHtml(e.role) + "</span>" +
        "</span>"
      );
    }).join("");

    var timeParts = [];
    if (fact.time.validFrom) timeParts.push("valid_from: " + fact.time.validFrom);
    if (fact.time.validUntil) timeParts.push("valid_until: " + fact.time.validUntil);
    if (fact.time.expires) {
      var exp = "expires: " + fact.time.expires;
      if (fact.time.lifetime) exp += " (" + fact.time.lifetime + ")";
      timeParts.push(exp);
    }

    return (
      '<article class="' + cardClasses.join(" ") + '" role="button" tabindex="0" data-fact-id="' + escapeHtml(fact.id) + '" aria-pressed="false">' +
        '<div class="fact-top">' +
          '<div class="fact-badges">' +
            '<span class="badge ' + statusBadgeClass(fact.status) + '">' + escapeHtml(fact.status) + "</span>" +
            classBadge +
            traitsHtml +
          "</div>" +
          '<span class="fact-id">' + escapeHtml(fact.id) + "</span>" +
        "</div>" +
        '<p class="fact-sentence">' + escapeHtml(fact.sentence) + "</p>" +
        relationHtml +
        '<div class="fact-quotes">' + quotesHtml + "</div>" +
        '<div class="fact-entities" aria-label="Linked entities">' + entitiesHtml + "</div>" +
        '<div class="fact-time">' +
          timeParts.map(function (p) { return "<span>" + escapeHtml(p) + "</span>"; }).join("") +
        "</div>" +
      "</article>"
    );
  }).join("");

  // Interactive linking state
  var pinned = null; // { kind: "fact" | "sentence", id: string } | null
  var hovered = null; // { kind: "fact" | "sentence", id: string } | null

  var passageScroller = document.getElementById("passage-scroller");
  var factsScroller = document.getElementById("facts-scroller");
  var selectionLabel = document.getElementById("selection-label");
  var clearBtn = document.getElementById("clear-selection");

  var desktopMedia = window.matchMedia("(min-width: 860px)");

  function isDesktop() {
    return desktopMedia.matches;
  }

  function scrollElementIntoContainer(el, container, allowPageScroll) {
    if (!el) return;
    if (isDesktop() && container) {
      var containerRect = container.getBoundingClientRect();
      var elRect = el.getBoundingClientRect();
      var isVisible = elRect.top >= containerRect.top + 12 && elRect.bottom <= containerRect.bottom - 12;
      if (!isVisible) {
        var targetTop = container.scrollTop + (elRect.top - containerRect.top) - (container.clientHeight - elRect.height) / 2;
        container.scrollTo({ top: Math.max(0, targetTop), behavior: "smooth" });
      }
    } else if (allowPageScroll) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }

  function getActiveSelection() {
    return hovered || pinned;
  }

  function renderHighlights(scrollTarget) {
    var active = getActiveSelection();
    var activeSentenceIds = {};
    var activeFactIds = {};
    var activeTurnIds = {};

    if (active) {
      if (active.kind === "fact") {
        activeFactIds[active.id] = true;
        (factToSentences[active.id] || []).forEach(function (sid) {
          activeSentenceIds[sid] = true;
          if (sentenceLookup[sid]) activeTurnIds[sentenceLookup[sid].turnId] = true;
        });
      } else if (active.kind === "sentence") {
        activeSentenceIds[active.id] = true;
        if (sentenceLookup[active.id]) activeTurnIds[sentenceLookup[active.id].turnId] = true;
        (sentenceToFacts[active.id] || []).forEach(function (fid) {
          activeFactIds[fid] = true;
        });
      }
    }

    var hasActive = Boolean(active);

    // Update sentences
    turnsList.querySelectorAll(".sentence-cited").forEach(function (el) {
      var sid = el.getAttribute("data-sentence-id");
      el.classList.toggle("is-active", Boolean(activeSentenceIds[sid]));
    });

    // Update turns
    turnsList.querySelectorAll(".turn-card").forEach(function (el) {
      var tid = el.getAttribute("data-turn-id");
      el.classList.toggle("has-active-cite", Boolean(activeTurnIds[tid]));
    });

    // Update fact cards
    factsList.querySelectorAll(".fact-card").forEach(function (el) {
      var fid = el.getAttribute("data-fact-id");
      var isMatch = Boolean(activeFactIds[fid]);
      el.classList.toggle("is-active", isMatch);
      el.classList.toggle("is-dimmed", hasActive && !isMatch);
      el.setAttribute("aria-pressed", String(Boolean(pinned && pinned.kind === "fact" && pinned.id === fid)));
    });

    // Update status bar
    if (pinned) {
      clearBtn.hidden = false;
      if (pinned.kind === "fact") {
        var citedCount = (factToSentences[pinned.id] || []).length;
        selectionLabel.textContent =
          "Pinned " + pinned.id + " · " + citedCount + (citedCount === 1 ? " cited sentence" : " cited sentences");
      } else {
        var factCount = (sentenceToFacts[pinned.id] || []).length;
        var sInfo = sentenceLookup[pinned.id];
        selectionLabel.textContent =
          "Pinned " + (sInfo ? sInfo.speaker + " (" + sInfo.timestamp + ")" : pinned.id) +
          " · " + factCount + (factCount === 1 ? " citing fact" : " citing facts");
      }
    } else if (hovered) {
      clearBtn.hidden = true;
      if (hovered.kind === "fact") {
        selectionLabel.textContent = "Inspecting " + hovered.id;
      } else {
        var hInfo = sentenceLookup[hovered.id];
        selectionLabel.textContent = "Inspecting quote at " + (hInfo ? hInfo.timestamp : hovered.id);
      }
    } else {
      clearBtn.hidden = true;
      selectionLabel.textContent = "No selection pinned";
    }

    // Scroll opposite pane into view when requested
    if (scrollTarget === "to-passage" && active && active.kind === "fact") {
      var firstSid = (factToSentences[active.id] || [])[0];
      if (firstSid) {
        var sEl = turnsList.querySelector('[data-sentence-id="' + firstSid + '"]');
        scrollElementIntoContainer(sEl, passageScroller, Boolean(pinned && pinned.kind === "fact" && pinned.id === active.id));
      }
    } else if (scrollTarget === "to-facts" && active && active.kind === "sentence") {
      var firstFid = (sentenceToFacts[active.id] || [])[0];
      if (firstFid) {
        var fEl = factsList.querySelector('[data-fact-id="' + firstFid + '"]');
        scrollElementIntoContainer(fEl, factsScroller, Boolean(pinned && pinned.kind === "sentence" && pinned.id === active.id));
      }
    }
  }

  function togglePin(kind, id) {
    if (pinned && pinned.kind === kind && pinned.id === id) {
      pinned = null;
      hovered = null;
      renderHighlights(null);
    } else {
      pinned = { kind: kind, id: id };
      hovered = null;
      renderHighlights(kind === "fact" ? "to-passage" : "to-facts");
    }
  }

  // Fact card interactions
  factsList.querySelectorAll(".fact-card").forEach(function (card) {
    var fid = card.getAttribute("data-fact-id");

    card.addEventListener("mouseenter", function () {
      if (!isDesktop()) return;
      hovered = { kind: "fact", id: fid };
      renderHighlights("to-passage");
    });

    card.addEventListener("mouseleave", function () {
      if (!isDesktop()) return;
      if (hovered && hovered.kind === "fact" && hovered.id === fid) {
        hovered = null;
        renderHighlights(null);
      }
    });

    card.addEventListener("click", function () {
      togglePin("fact", fid);
    });

    card.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        togglePin("fact", fid);
      }
    });
  });

  // Cited sentence interactions
  turnsList.querySelectorAll(".sentence-cited").forEach(function (span) {
    var sid = span.getAttribute("data-sentence-id");

    span.addEventListener("mouseenter", function () {
      if (!isDesktop()) return;
      hovered = { kind: "sentence", id: sid };
      renderHighlights("to-facts");
    });

    span.addEventListener("mouseleave", function () {
      if (!isDesktop()) return;
      if (hovered && hovered.kind === "sentence" && hovered.id === sid) {
        hovered = null;
        renderHighlights(null);
      }
    });

    span.addEventListener("click", function (e) {
      e.stopPropagation();
      togglePin("sentence", sid);
    });

    span.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        togglePin("sentence", sid);
      }
    });
  });

  clearBtn.addEventListener("click", function () {
    pinned = null;
    hovered = null;
    renderHighlights(null);
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && (pinned || hovered)) {
      pinned = null;
      hovered = null;
      renderHighlights(null);
    }
  });
})();
