import re

with open('scratch_html.html', 'r', encoding='utf-8') as f:
    html_content = f.read()

# remove all mock script inside <script> except theme logic
mock_script_re = re.compile(r'/\* ---- Before / After comparison slider ---- \*/.*?(?=\}\)\(\);\n\s*</script>)', re.DOTALL)
html_content = mock_script_re.sub('', html_content)

# Replace IDs or add them where needed

# playBtn -> playPauseBtn
html_content = html_content.replace('id="playBtn"', 'id="playPauseBtn"')

# scrub -> scrubber
html_content = html_content.replace('id="scrub"', 'id="scrubber"')

# after badge
html_content = html_content.replace('<span class="ba-badge badge-after">After</span>', '<span class="ba-badge badge-after" id="afterBadge">After</span>')

# original empty
html_content = html_content.replace('<span class="ba-badge badge-before">Before</span>', '<span class="ba-badge badge-before">Before</span><div id="originalEmpty" style="position:absolute; inset:0; display:grid; place-items:center; color:#fff; font-family:var(--mono); font-size:14px; background:rgba(0,0,0,0.5); z-index:4">No video selected</div>')

# processed empty
html_content = html_content.replace('<span class="ba-badge badge-after" id="afterBadge">After</span>', '<span class="ba-badge badge-after" id="afterBadge">After</span><div id="processedEmpty" style="position:absolute; inset:0; display:grid; place-items:center; color:#fff; font-family:var(--mono); font-size:14px; background:rgba(0,0,0,0.5); z-index:4">Processing will appear here</div>')

# video and img elements
html_content = html_content.replace(
    '<svg class="frame" viewBox="0 0 1280 720" preserveAspectRatio="xMidYMid slice" aria-hidden="true"><use href="#scene"/></svg>',
    '<video id="processedVideo" class="frame" style="object-fit: contain; width: 100%; height: 100%; background: #000" hidden></video><img id="processedImage" class="frame" style="object-fit: contain; width: 100%; height: 100%; background: #000" hidden>'
)

html_content = html_content.replace(
    '<svg class="frame" viewBox="0 0 1280 720" preserveAspectRatio="xMidYMid slice" aria-hidden="true">\n                <use href="#scene"/><use href="#wm-bbox"/>\n              </svg>',
    '<video id="originalVideo" class="frame" style="object-fit: contain; width: 100%; height: 100%; background: #000" hidden></video><img id="originalImage" class="frame" style="object-fit: contain; width: 100%; height: 100%; background: #000" hidden>'
)

# metadata
html_content = re.sub(r'<dl class="rows">.*?</dl>', '<div id="metadata" class="rows">Waiting for video</div>', html_content, flags=re.DOTALL)

# detection
html_content = re.sub(r'<div class="detect">.*?</div>\n                </div>', '<div class="detect" id="detection">Waiting for detection</div>\n                <div id="autoPresetSummary" style="margin-top: 10px; font-size: 13px;"></div>\n                <button id="detectBtn" class="btn btn-ghost btn-sm" type="button" disabled style="margin-top:10px;"><svg class="ic" aria-hidden="true"><use href="#i-refresh"/></svg>Detect Again</button>\n                </div>', html_content, flags=re.DOTALL)

# processing bar
html_content = html_content.replace('<div class="bar"><i></i></div>', '<div class="bar"><i id="progressBar"></i></div>')
html_content = html_content.replace('<b>63%</b>', '<b id="progressText">0%</b>')
html_content = html_content.replace('<h3 id="procTitle">Processing video…</h3>', '<h3 id="status">Waiting...</h3>')
html_content = html_content.replace('id="stopBtn"', 'id="cancelBtn"')

# buttons
html_content = html_content.replace(
    '<button class="btn btn-primary btn-lg" type="button">\n                    <svg class="ic" aria-hidden="true"><use href="#i-spark"/></svg>Remove Watermark &amp; Export\n                  </button>',
    '<button id="processBtn" class="btn btn-primary btn-lg" type="button" disabled>\n                    <svg class="ic" aria-hidden="true"><use href="#i-spark"/></svg>Remove Watermark &amp; Export\n                  </button>'
)

html_content = html_content.replace(
    '<button class="btn btn-ghost" type="button">Reset</button>',
    '<button id="resetBtn" class="btn btn-ghost" type="button" disabled>Reset</button>'
)

html_content = html_content.replace(
    '<button class="btn btn-primary btn-lg" type="button">\n              <svg class="ic" aria-hidden="true"><use href="#i-download"/></svg>Download Video\n            </button>',
    '<a id="downloadBtn" class="btn btn-primary btn-lg" tabindex="-1" aria-disabled="true">\n              <svg class="ic" aria-hidden="true"><use href="#i-download"/></svg>Download Video\n            </a>'
)
html_content = html_content.replace(
    '<button class="btn btn-lg" type="button">\n              <svg class="ic" aria-hidden="true"><use href="#i-refresh"/></svg>Process Another Video\n            </button>',
    '<button class="btn btn-lg" type="button" onclick="document.getElementById(\'resetBtn\').click()">\n              <svg class="ic" aria-hidden="true"><use href="#i-refresh"/></svg>Process Another Video\n            </button>'
)

# advanced settings
advanced_settings_html = """
            <div class="field">
              <label>Alpha Gain: <output id="alphaGainValue">1.00</output></label>
              <input type="range" id="alphaGain" min="0.1" max="3" step="0.1" value="1.0">
            </div>
            <div class="field">
              <label>Edge Denoise Strength: <output id="edgeDenoiseStrengthValue">0.50</output></label>
              <input type="range" id="edgeDenoiseStrength" min="0" max="1" step="0.1" value="0.5">
            </div>
            <div class="field">
              <label>Residual Cleanup: <output id="residualCleanupValue">0.50</output></label>
              <input type="range" id="residualCleanup" min="0" max="1" step="0.1" value="0.5">
            </div>
            <div class="field">
              <label for="denoiseBackend">Denoise Backend</label>
              <select id="denoiseBackend">
                  <option value="allenk_fdncnn_browser_spike">allenk_fdncnn_browser_spike</option>
                  <option value="none">none</option>
              </select>
            </div>
            <div class="field">
              <label for="videoBitrateMbps">Video Bitrate (Mbps)</label>
              <input type="number" id="videoBitrateMbps" value="5" step="1" class="btn-sm" style="width:100%; border:1px solid var(--border-2); background:var(--surface); border-radius:8px; padding:0 10px;">
            </div>
            <div class="field">
              <label for="sampleCount">Sample Count</label>
              <input type="number" id="sampleCount" value="10" step="1" class="btn-sm" style="width:100%; border:1px solid var(--border-2); background:var(--surface); border-radius:8px; padding:0 10px;">
            </div>
            <div class="checks">
              <label class="check"><input type="checkbox" id="adaptiveAlpha" checked> Adaptive Alpha</label>
              <label class="check"><input type="checkbox" id="highQualityCleanup" checked> High Quality Cleanup</label>
              <label class="check"><input type="checkbox" id="allowLowConfidence"> Allow Low Confidence</label>
            </div>
"""

html_content = re.sub(r'<div class="adv-body">.*?</div>\n        </details>', '<div class="adv-body">' + advanced_settings_html + '</div>\n        </details>', html_content, flags=re.DOTALL)


# append missing hidden elements and scripts
append_html = """
    <div id="batchQueue" style="display: none;"></div>
    <button id="relocatedReviewPresetBtn" hidden>Relocated</button>
    <div id="comparePlayer" style="display: none;"></div>

    <script type="module" src="video-app.js"></script>
"""
html_content = html_content.replace('</body>', append_html + '\n</body>')


with open('public/video-preview.html', 'w', encoding='utf-8') as f:
    f.write(html_content)
