let selectedPlaylistId = null;
let trackList = [];

function handleTypeChange() {
  const type = document.getElementById("checkType").value;
  const urlInput = document.getElementById("urlInput");
  const playlistSelect = document.getElementById("playlistSelect");
  const loadBtn = document.getElementById("loadPlaylistsBtn");
  const limitValue = document.getElementById("limitValue");
  const rangeInputs = document.getElementById("rangeInputs");

  // Reset
  urlInput.style.display = "none";
  playlistSelect.style.display = "none";
  loadBtn.style.display = "none";
  selectedPlaylistId = null;
  rangeInputs.style.display = "none";

  if (type === "url") {
    urlInput.style.display = "block";
    urlInput.placeholder = "Paste Spotify URL";
    limitValue.style.display = "none";
  } else if (type === "myplaylists") {
    loadBtn.style.display = "block";
    limitValue.style.display = "none";
    rangeInputs.style.display = "grid";
  } else if (type === "saved") {
    limitValue.style.display = "block";
    urlInput.style.display = "none";
  } else if (type === "search") {
    urlInput.style.display = "block";
    urlInput.placeholder = "Enter search query";
    limitValue.style.display = "block";
  }
}

function loadMyPlaylists() {
  document.getElementById("loading").style.display = "block";
  document.getElementById("results").style.display = "none";

  fetch("/api/my-playlists")
    .then((response) => response.json())
    .then((data) => {
      document.getElementById("loading").style.display = "none";

      if (data.error) {
        alert("Error loading playlists: " + data.error);
        return;
      }

      const playlistSelect = document.getElementById("playlistSelect");
      playlistSelect.style.display = "block";

      let html =
        '<h3 style="padding: 10px; color: #1DB954;">Select a Playlist:</h3>';
      data.playlists.forEach((playlist) => {
        html += `
                            <div class="playlist-item" onclick="selectPlaylist('${
                              playlist.id
                            }', '${playlist.name.replace(/'/g, "\\'")}')">
                                <div class="playlist-info">
                                    <div class="playlist-name">${
                                      playlist.name
                                    }</div>
                                    <div class="playlist-meta">${
                                      playlist.tracks
                                    } tracks • ${playlist.owner}</div>
                                    
                                </div>
                                <div>▶</div>
                            </div>
                        `;
      });
      playlistSelect.innerHTML = html;
    })
    .catch((error) => {
      document.getElementById("loading").style.display = "none";
      alert("Error: " + error);
    });
}




function selectPlaylist(playlistId, playlistName, event) {
  selectedPlaylistId = playlistId;

  const items = document.querySelectorAll(".playlist-item");
  items.forEach(i => i.style.background = "#444");

  if (event?.currentTarget) {
    event.currentTarget.style.background = "#1DB954";
  }
}


function checkCopyright() {
  const type = document.getElementById("checkType").value;
  const input = document.getElementById("urlInput").value;
  const limit = document.getElementById("limitValue").value || 20;

  document.getElementById("loading").style.display = "block";
  document.getElementById("results").style.display = "none";

  let url = "";
  if (type === "url") {
    url = `/api/check-url?url=${encodeURIComponent(input)}`;
  } else if (type === "myplaylists") {
    if (!selectedPlaylistId) {
      document.getElementById("loading").style.display = "none";
      alert("Please select a playlist first!");
      return;
    }
    const s = document.getElementById("rangeStart").value;
    const e = document.getElementById("rangeEnd").value;
    const range = s && e ? `&start=${s}&end=${e}` : "";
    url = `/api/check-playlist?playlist_id=${selectedPlaylistId}${range}`;
  } else if (type === "saved") {
    url = `/api/saved-tracks?limit=${limit}`;
  } else if (type === "search") {
    url = `/api/search?query=${encodeURIComponent(input)}&limit=${limit}`;
  }

  fetch(url)
    .then((response) => response.json())
    .then((data) => {
      console.log("FULL RESPONSE:", data);
      console.log("TRACKS RETURNED:", data.tracks);

      trackList = data.tracks; //for tracklist

      document.getElementById("loading").style.display = "none";
      document.getElementById("results").style.display = "block";

      if (data.error) {
        document.getElementById("resultsTitle").textContent =
          "Error: " + data.error;
        document.getElementById("trackList").innerHTML = "";
        return;
      }

      document.getElementById("resultsTitle").textContent =
        data.title || `Found ${data.tracks.length} tracks`;

      let html = "";
      data.tracks.forEach((track) => {
        html += `
                            <div class="track" onclick="openTrackDetails('${
                              track.id
                            }')">
                                <div class="track-name">${track.name}</div>
                                <button onclick="event.stopPropagation(); addTrack('${
                                  track.id
                                }')" style="margin-left: auto; background-color: transparent; border: none; cursor: pointer; padding: 8px;">
                                <i class="fas fa-bookmark" style="color: white; font-size: 24px;"></i>
                                </button>


                                <div class="track-artist">${track.artist}</div>
                                <div style="display:flex; gap:10px; align-items:center; margin-top:8px; flex-wrap: wrap;">
                                    <span class="license-badge ${
                                      track.license?.is_free
                                        ? "license-ok"
                                        : "license-bad"
                                    }">
                                        ${
                                          track.license?.is_free
                                            ? "✓ Copyright-free (heuristic)"
                                            : "✕ Likely copyrighted"
                                        }
                                    </span>
                                    <span style="font-size:12px; color:#aaa;">Conf: ${
                                      track.license?.confidence ?? 0
                                    }</span>
                                </div>
                                <div class="copyright">
                                    ${
                                      track.copyrights.length > 0
                                        ? track.copyrights
                                            .map((c) => `${c.type}: ${c.text}`)
                                            .join("<br>")
                                        : "⚠️ No copyright information found"
                                    }
                                </div>
                            </div>
                        `;
      });
      document.getElementById("trackList").innerHTML = html;
    })
    .catch((error) => {
      document.getElementById("loading").style.display = "none";
      alert("Error: " + error);
    });
}

// Initialize on load
handleTypeChange();

function openTrackDetails(trackId) {
  if (!trackId) return;
  const overlay = document.getElementById("modalOverlay");
  const content = document.getElementById("modalContent");
  const title = document.getElementById("modalTitle");
  overlay.style.display = "flex";
  content.innerHTML = "Loading…";
  fetch(`/api/track-details?track_id=${trackId}`)
    .then((r) => r.json())
    .then((data) => {
      if (data.error) {
        content.innerHTML = "Error: " + data.error;
        return;
      }
      title.textContent = `${data.track.name} — ${data.track.artist}`;
      const l = data.license;
      const badge = `<span class="license-badge ${
        l.is_free ? "license-ok" : "license-bad"
      }">${
        l.is_free ? "✓ Copyright-free (heuristic)" : "✕ Likely copyrighted"
      }</span>`;
      let featuresHtml = "";
      if (data.audio_features && data.audio_features._has_data) {
        featuresHtml = `
                            <div class="detail-box">
                                <strong>Audio Features</strong><br>
                                Tempo: ${data.audio_features.tempo} BPM<br>
                                Key: ${data.audio_features.key} • Mode: ${data.audio_features.mode}<br>
                                Danceability: ${data.audio_features.danceability}<br>
                                Energy: ${data.audio_features.energy}
                            </div>`;
      }
      content.innerHTML = `
                        <div style="margin-bottom: 10px; display:flex; gap:10px; align-items:center;">${badge}<span style="font-size:12px; color:#aaa;">Conf: ${
        l.confidence
      }</span>
                            
                            </div>
                        <div class="details-grid">
                            <div class="detail-box">
                                <strong>Album</strong><br>${data.album.name} (${
        data.album.release_date
      })<br>Label: ${data.album.label || "—"}
                            </div>
                            <div class="detail-box">
                                <strong>Popularity</strong><br>${
                                  data.track.popularity
                                }/100<br><strong>Explicit:</strong> ${
        data.track.explicit ? "Yes" : "No"
      }
                            </div>
                            ${featuresHtml}
                            <div class="detail-box">
                                <strong>Signals</strong><br>
                                Positive: ${
                                  (l.signals.positive || []).join(", ") ||
                                  "none"
                                }<br>
                                Negative: ${
                                  (l.signals.negative || []).join(", ") ||
                                  "none"
                                }
                            </div>
                            <div class="detail-box" style="grid-column: 1 / -1;">
                                <strong>Copyrights</strong><br>
                                ${
                                  (data.album.copyrights || [])
                                    .map((c) => `${c.type}: ${c.text}`)
                                    .join("<br>") || "None"
                                }
                            </div>
                        </div>
                    `;
    })
    .catch((err) => {
      content.innerHTML = "Error: " + err;
    });
}

function closeModal(e) {
  document.getElementById("modalOverlay").style.display = "none";
}

let currentTrackId = null;

function addTrack(trackId) {
  if (!trackId) return;

  currentTrackId = trackId;
  const overlay = document.getElementById("playlistModalOverlay");
  const body = document.getElementById("playlistModalBody");
  const title = document.getElementById("playlistModalTitle");

  overlay.style.display = "flex";
  body.innerHTML = "Loading my playlists";

  fetch("/api/my-playlists")
    .then((r) => r.json())
    .then((data) => {
      const playlists = data.playlists;

      let optionsHtml = '<option value="">Choose a playlist</option>';

      playlists.forEach((playlist) => {
        optionsHtml += `<option value="${playlist.id}">${playlist.name}</option>`;
      });

      body.innerHTML = `
        <select id="playlistDropdown" >
          ${optionsHtml}
        </select>
        <div style="display: flex; gap: 10px; justify-content: flex-end; margin-top: 20px;">
          <button class="closePlaylistModalBtn" onclick="closePlaylistModal()">Cancel</button>
          <button class="confirmPlaylistAdd" onclick="confirmAddToPlaylist()">Add to Playlist</button>
        </div>
      `;
    })
    .catch((err) => {
      console.error("Full error:", err);
      body.innerHTML = "Error loading playlists: " + err;
    });
}

// event param optional bc we can close by clicking cancel btn or by clicking outside of modal
function closePlaylistModal(event) {
  if (
    event &&
    event.target !== document.getElementById("playlistModalOverlay")
  ) {
    return;
  }
  document.getElementById("playlistModalOverlay").style.display = "none";
  currentTrackId = null; // remove because we are closing modal and dont need this
}

function confirmAddToPlaylist() {
  const playlistId = document.getElementById("playlistDropdown").value;
  const body = document.getElementById("playlistModalBody");

  if (!playlistId) {
    alert("You must select a playlist");
    return;
  }

  body.innerHTML = "Adding track";

  fetch("/api/add-playlist-items", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      track_id: currentTrackId,
      playlist_id: playlistId,
    }),
  })
    .then((r) => r.json())
    .then((data) => {
      if (data.error) {
        body.innerHTML = "Error adding song to the playlist: " + data.error;
      } else {
        body.innerHTML = "Track added!";
        setTimeout(() => closePlaylistModal(), 1500);
      }
    })
    .catch((err) => {
      body.innerHTML = "Error adding song to playlist " + err;
    });
}
