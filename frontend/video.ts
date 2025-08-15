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