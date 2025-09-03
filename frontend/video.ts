import init, { 
  convert_timestamps, 
  render_component_by_name, 
  render_chat_logs, 
  render_tag_category_manager, 
  render_transcription_table 
} from "../app/static/wasm/yappr_wasm.js";

class VideoPage {
  private wasmReady = false;
  private videoId: number;

  constructor(videoId: number) {
    this.videoId = videoId;
  }

  async init() {
    await this.initWasm();
    this.setupGlobalFunctions();
    this.setupVideoLinking();
    await this.renderInitialComponents();
  }

  private async initWasm() {
    // Get WASM URL from meta tag or construct it
    const wasmUrl = this.getWasmUrl();
    await init(wasmUrl);
    this.wasmReady = true;
  }

  private getWasmUrl(): string {
    // Look for meta tag with WASM URL, fallback to constructing it
    const wasmMeta = document.querySelector('meta[name="wasm-url"]') as HTMLMetaElement;
    if (wasmMeta) {
      return wasmMeta.content;
    }
    
    // Fallback - construct URL (this might need adjustment based on your routing)
    const version = document.querySelector('meta[name="version"]')?.getAttribute('content') || '';
    return `/static/wasm/yappr_wasm_bg.wasm${version ? `?v=${version}` : ''}`;
  }

  private setupGlobalFunctions() {
    // Expose functions to global scope for template compatibility
    (window as any).renderTagCategoryManager = () => {
      if (this.wasmReady) {
        render_tag_category_manager("tag-category-manager");
      } else {
        console.log("WASM not ready yet");
      }
    };

    (window as any).renderChatLogs = (videoId?: number) => {
      const id = videoId || this.videoId;
      if (this.wasmReady) {
        render_chat_logs(id, "chat-logs-container");
      } else {
        console.log("WASM not ready yet");
      }
    };

    (window as any).renderTranscriptionTable = (videoId?: number) => {
      const id = videoId || this.videoId;
      if (this.wasmReady) {
        render_transcription_table(id, "transcription-segments-container");
      } else {
        console.log("WASM not ready yet");
      }
    };

    (window as any).convertTimestamps = () => {
      if (this.wasmReady) {
        convert_timestamps();
      } else {
        console.log("WASM not ready yet");
      }
    };
  }

  private async renderInitialComponents() {
    if (!this.wasmReady) {
      console.error("WASM not ready for initial render");
      return;
    }

    // Render initial components
    render_tag_category_manager("tag-category-manager");
    render_chat_logs(this.videoId, "chat-logs-container");
    render_transcription_table(this.videoId, "transcription-segments-container");
  }

  // Public methods for manual triggering
  public renderTagCategoryManager() {
    if (this.wasmReady) {
      render_tag_category_manager("tag-category-manager");
    }
  }

  public renderChatLogs() {
    if (this.wasmReady) {
      render_chat_logs(this.videoId, "chat-logs-container");
    }
  }

  public renderTranscriptionTable() {
    if (this.wasmReady) {
      render_transcription_table(this.videoId, "transcription-segments-container");
    }
  }

  public convertTimestamps() {
    if (this.wasmReady) {
      convert_timestamps();
    }
  }

  private setupVideoLinking() {
    const previewButton = document.getElementById('preview-link-btn');
    if (previewButton) {
      previewButton.addEventListener('click', () => this.showLinkPreview());
    }

    const applyOffsetBtn = document.getElementById('applyOffsetBtn');
    if (applyOffsetBtn) {
      applyOffsetBtn.addEventListener('click', () => this.applyOffsetAdjustment());
    }
  }

  private async showLinkPreview() {
    const modal = document.getElementById('linkPreviewModal') as any;
    const modalInstance = new (window as any).bootstrap.Modal(modal);
    const contentDiv = document.getElementById('link-preview-content');
    
    if (!contentDiv) return;

    // Show loading state
    contentDiv.innerHTML = `
      <div class="text-center py-3">
        <div class="spinner-border" role="status">
          <span class="visually-hidden">Loading...</span>
        </div>
        <p class="mt-2">Finding potential video matches...</p>
      </div>
    `;
    
    modalInstance.show();

    try {
      const response = await fetch(`/video/${this.videoId}/link_preview`);
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || 'Failed to fetch video links');
      }

      this.renderLinkPreview(data, contentDiv);
    } catch (error) {
      console.error('Error fetching link preview:', error);
      contentDiv.innerHTML = `
        <div class="alert alert-danger">
          <i class="bi bi-exclamation-triangle me-2"></i>
          Error: ${error instanceof Error ? error.message : 'Failed to load video links'}
        </div>
      `;
    }
  }

  private renderLinkPreview(data: any, contentDiv: HTMLElement) {
    const { video, potential_matches } = data;
    
    let html = `
      <div class="mb-4">
        <h6>Current Video</h6>
        <div class="card">
          <div class="card-body">
            <h6 class="card-title">${this.escapeHtml(video.title)}</h6>
            ${video.estimated_date ? 
              `<p class="text-muted mb-1"><i class="bi bi-calendar me-1"></i>Extracted Date: ${new Date(video.estimated_date).toLocaleDateString()}</p>` 
              : ''}
            <p class="text-muted mb-0">
              <i class="bi bi-gear me-1"></i>Title Parsing: ${video.title_parsing_enabled ? 'Enabled' : 'Disabled'}
            </p>
          </div>
        </div>
      </div>
    `;

    if (potential_matches.length === 0) {
      html += `
        <div class="alert alert-info">
          <i class="bi bi-info-circle me-2"></i>
          No potential matches found. This could be because:
          <ul class="mb-0 mt-2">
            <li>No videos match the duration criteria (±2 seconds)</li>
            <li>Title date parsing is disabled and no date matches found</li>
            <li>The source channel has no videos in the date range</li>
          </ul>
        </div>
      `;
    } else {
      html += `
        <div class="mb-3">
          <h6>Potential Matches <span class="badge bg-secondary">${potential_matches.length}</span></h6>
          <p class="text-muted small">Click "Link Video" to confirm the connection</p>
        </div>
      `;

      potential_matches.forEach((match: any, index: number) => {
        const { video: sourceVideo, match_reasons, duration_diff, time_diff_hours } = match;
        const badgeClass = match_reasons.length > 1 ? 'bg-success' : 'bg-primary';
        
        html += `
          <div class="card mb-3">
            <div class="card-body">
              <div class="d-flex justify-content-between align-items-start">
                <div class="flex-grow-1">
                  <h6 class="card-title mb-1">${this.escapeHtml(sourceVideo.title)}</h6>
                  <div class="d-flex flex-wrap gap-1 mb-2">
                    ${match_reasons.map((reason: string) => 
                      `<span class="badge ${badgeClass}">${this.capitalizeFirst(reason)} Match</span>`
                    ).join('')}
                  </div>
                  <div class="row text-muted small">
                    <div class="col-sm-6">
                      <i class="bi bi-calendar me-1"></i>${new Date(sourceVideo.uploaded).toLocaleDateString()}
                    </div>
                    <div class="col-sm-6">
                      <i class="bi bi-clock me-1"></i>${this.formatDuration(sourceVideo.duration)}
                    </div>
                  </div>
                  <div class="row text-muted small mt-1">
                    <div class="col-sm-6">
                      <i class="bi bi-activity me-1"></i>Duration Diff: ${duration_diff.toFixed(1)}s
                    </div>
                    ${time_diff_hours !== null ? 
                      `<div class="col-sm-6">
                        <i class="bi bi-clock-history me-1"></i>Time Diff: ${time_diff_hours.toFixed(1)}h
                      </div>` : ''}
                  </div>
                </div>
                <div class="ms-3">
                  <a href="${sourceVideo.url}" target="_blank" class="btn btn-outline-secondary btn-sm me-2">
                    <i class="bi bi-box-arrow-up-right"></i>
                  </a>
                  <button class="btn btn-primary btn-sm" onclick="videoPage.confirmVideoLink(${sourceVideo.id}, \`${sourceVideo.title.replace(/`/g, '\\`').replace(/\\/g, '\\\\')}\`)">
                    Link Video
                  </button>
                </div>
              </div>
            </div>
          </div>
        `;
      });
    }

    contentDiv.innerHTML = html;
  }

  public async confirmVideoLink(sourceVideoId: number, sourceTitle: string) {
    if (!confirm(`Link this video to "${sourceTitle}"?\n\nThis action will connect the videos, you can adjust the offset later.`)) {
      return;
    }

    try {
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      };

      // Add CSRF token if available
      if ((window as any).csrfToken) {
        headers['X-CSRFToken'] = (window as any).csrfToken;
      }

      const response = await fetch(`/video/${this.videoId}/link_confirm`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ source_video_id: sourceVideoId })
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || 'Failed to link video');
      }

      // Close modal and reload page to show the link
      const modal = document.getElementById('linkPreviewModal') as any;
      const modalInstance = (window as any).bootstrap.Modal.getInstance(modal);
      modalInstance.hide();

      // Show success message and reload
      alert(data.message);
      window.location.reload();

    } catch (error) {
      console.error('Error linking video:', error);
      alert(`Error: ${error instanceof Error ? error.message : 'Failed to link video'}`);
    }
  }

  public async applyOffsetAdjustment() {
    const offsetInput = document.getElementById('offsetAdjustment') as HTMLInputElement;
    const statusDiv = document.getElementById('offset-adjust-status');
    
    if (!offsetInput || !statusDiv) return;

    const offsetValue = parseFloat(offsetInput.value);
    
    if (isNaN(offsetValue)) {
      statusDiv.innerHTML = '<div class="alert alert-danger">Please enter a valid number</div>';
      return;
    }

    if (offsetValue === 0) {
      statusDiv.innerHTML = '<div class="alert alert-warning">No adjustment needed - offset is 0</div>';
      return;
    }

    if (!confirm(`Adjust timing by ${offsetValue > 0 ? '+' : ''}${offsetValue} seconds?\n\nThis will modify all timestamp mappings for this video.`)) {
      return;
    }

    try {
      statusDiv.innerHTML = '<div class="text-center"><div class="spinner-border spinner-border-sm me-2"></div>Applying offset adjustment...</div>';

      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      };

      // Add CSRF token if available
      if ((window as any).csrfToken) {
        headers['X-CSRFToken'] = (window as any).csrfToken;
      }

      const response = await fetch(`/video/${this.videoId}/adjust_offset`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ offset_adjustment: offsetValue })
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || 'Failed to adjust offset');
      }

      statusDiv.innerHTML = `<div class="alert alert-success"><i class="bi bi-check-circle me-2"></i>${data.message}</div>`;
      
      // Reset input
      offsetInput.value = '0.0';
      
      // Auto-close modal after 2 seconds
      setTimeout(() => {
        const modal = document.getElementById('offsetAdjustModal') as any;
        const modalInstance = (window as any).bootstrap.Modal.getInstance(modal);
        if (modalInstance) {
          modalInstance.hide();
        }
      }, 2000);

    } catch (error) {
      console.error('Error adjusting offset:', error);
      statusDiv.innerHTML = `<div class="alert alert-danger"><i class="bi bi-exclamation-triangle me-2"></i>Error: ${error instanceof Error ? error.message : 'Failed to adjust offset'}</div>`;
    }
  }

  private escapeHtml(text: string): string {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  private capitalizeFirst(str: string): string {
    return str.charAt(0).toUpperCase() + str.slice(1);
  }

  private formatDuration(seconds: number): string {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    
    if (hours > 0) {
      return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
  }
}

// Auto-initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
  // Get video ID from data attribute or meta tag
  const videoElement = document.querySelector('[data-video-id]') as HTMLElement;
  const videoIdMeta = document.querySelector('meta[name="video-id"]') as HTMLMetaElement;
  
  let videoId: number;
  
  if (videoElement?.dataset.videoId) {
    videoId = parseInt(videoElement.dataset.videoId, 10);
  } else if (videoIdMeta?.content) {
    videoId = parseInt(videoIdMeta.content, 10);
  } else {
    console.error("Video ID not found. Add data-video-id attribute or meta tag.");
    return;
  }

  const videoPage = new VideoPage(videoId);
  videoPage.init().catch(console.error);

  // Expose instance globally for debugging
  (window as any).videoPage = videoPage;
});

export default VideoPage;