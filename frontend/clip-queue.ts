// Clip queue functionality
declare global {
  interface Window {
    YT: any;
    onYouTubeIframeAPIReady: () => void;
    htmx: any;
    io: any;
  }
}

// Global variables
let ytPlayer: any = null;
let currentClipId: string | null = null;
let socket: any = null;
let autoPlayEnabled = false;
let isPlayerReady = false;

// YouTube API integration
function initializeYouTubeAPI(): void {
  // Load YouTube IFrame API
  const tag = document.createElement('script');
  tag.src = 'https://www.youtube.com/iframe_api';
  const firstScriptTag = document.getElementsByTagName('script')[0];
  firstScriptTag.parentNode?.insertBefore(tag, firstScriptTag);
  
  // YouTube API ready callback
  window.onYouTubeIframeAPIReady = () => {
    console.log('YouTube API ready');
    initializePlayerIfNeeded();
  };
}

// Initialize YouTube player
function initializePlayer(videoId: string, startTime?: number): void {
  const playerElement = document.getElementById('youtube-player');
  if (!playerElement) return;
  
  if (ytPlayer) {
    ytPlayer.destroy();
  }
  
  ytPlayer = new window.YT.Player('youtube-player', {
    videoId: videoId,
    playerVars: {
      start: startTime || 0,
      autoplay: autoPlayEnabled ? 1 : 0,
      rel: 0,
      modestbranding: 1,
      controls: 1,
      showinfo: 0,
      fs: 1,
      cc_load_policy: 0,
      iv_load_policy: 3,
      autohide: 0
    },
    events: {
      onReady: onPlayerReady,
      onStateChange: onPlayerStateChange
    }
  });
}

// Player ready callback
function onPlayerReady(event: any): void {
  isPlayerReady = true;
  console.log('Player ready');
  
  // Apply autoplay setting
  if (autoPlayEnabled) {
    event.target.playVideo();
  }
}

// Player state change callback
function onPlayerStateChange(event: any): void {
  const state = event.data;
  
  // YT.PlayerState.ENDED = 0
  if (state === 0 && autoPlayEnabled) {
    // Video ended, move to next clip
    setTimeout(() => {
      playNextClip();
    }, 1000);
  }
}

// Initialize player if needed
function initializePlayerIfNeeded(): void {
  const playerContainer = document.getElementById('player-container');
  if (playerContainer && playerContainer.dataset.videoId) {
    initializePlayer(
      playerContainer.dataset.videoId,
      parseInt(playerContainer.dataset.startTime || '0')
    );
  }
}

// Twitch player integration
function initializeTwitchPlayer(videoId: string, startTime?: number): void {
  const playerElement = document.getElementById('twitch-player');
  if (!playerElement) return;
  
  const embedUrl = `https://player.twitch.tv/?video=${videoId}&parent=${window.location.hostname}&autoplay=${autoPlayEnabled}&t=${startTime || 0}s`;
  
  playerElement.innerHTML = `
    <iframe 
      src="${embedUrl}" 
      frameborder="0" 
      allowfullscreen="true" 
      scrolling="no" 
      style="width: 100%; height: 100%;">
    </iframe>
  `;
}

// WebSocket connection for real-time updates
function initializeWebSocket(): void {
  if (typeof window.io !== 'undefined') {
    socket = window.io();
    
    socket.on('connect', () => {
      console.log('Connected to WebSocket');
    });
    
    socket.on('queue_update', (data: any) => {
      console.log('Queue update received:', data);
      refreshQueueItems();
    });
    
    socket.on('disconnect', () => {
      console.log('Disconnected from WebSocket');
    });
  }
}

// Refresh queue items
function refreshQueueItems(): void {
  if (window.htmx) {
    window.htmx.ajax('GET', '/clip_queue/items', '#queue-items');
  }
}

// Autoplay management
function toggleAutoplay(): void {
  autoPlayEnabled = !autoPlayEnabled;
  localStorage.setItem('autoPlayEnabled', autoPlayEnabled.toString());
  
  const autoplayBtn = document.getElementById('autoplay-btn');
  if (autoplayBtn) {
    autoplayBtn.textContent = autoPlayEnabled ? 'Disable Autoplay' : 'Enable Autoplay';
    autoplayBtn.className = autoPlayEnabled ? 'btn btn-warning' : 'btn btn-success';
  }
}

// Load autoplay setting from localStorage
function loadAutoplaySetting(): void {
  const saved = localStorage.getItem('autoPlayEnabled');
  autoPlayEnabled = saved === 'true';
  
  const autoplayBtn = document.getElementById('autoplay-btn');
  if (autoplayBtn) {
    autoplayBtn.textContent = autoPlayEnabled ? 'Disable Autoplay' : 'Enable Autoplay';
    autoplayBtn.className = autoPlayEnabled ? 'btn btn-warning' : 'btn btn-success';
    autoplayBtn.addEventListener('click', toggleAutoplay);
  }
}

// Play next clip
function playNextClip(): void {
  const activeItem = document.querySelector('.queue-item.active');
  if (!activeItem) return;
  
  const queueItems = document.querySelectorAll('.queue-item:not(.watched)');
  let nextIndex = -1;
  
  // Find current item index
  for (let i = 0; i < queueItems.length; i++) {
    if (queueItems[i] === activeItem) {
      nextIndex = i + 1;
      break;
    }
  }
  
  // Play next item if available
  if (nextIndex >= 0 && nextIndex < queueItems.length) {
    const nextItem = queueItems[nextIndex] as HTMLElement;
    const clipId = nextItem.dataset.id;
    
    if (clipId) {
      playClip(clipId);
    }
  } else {
    // No more clips, show completion message
    showCompletionMessage();
  }
}

// Play specific clip
function playClip(clipId: string): void {
  currentClipId = clipId;
  localStorage.setItem('activeQueueItemId', clipId);
  
  // Update active item styling
  document.querySelectorAll('.queue-item').forEach(item => {
    item.classList.remove('active', 'bg-primary-subtle');
  });
  
  const activeItem = document.querySelector(`.queue-item[data-id="${clipId}"]`);
  if (activeItem) {
    activeItem.classList.add('active', 'bg-primary-subtle');
  }
  
  // Load player and details
  if (window.htmx) {
    window.htmx.ajax('GET', `/clip_queue/player/${clipId}`, '#player-container');
    window.htmx.ajax('GET', `/clip_queue/details/${clipId}`, '#clip-details');
  }
}

// Mark clip as watched
function markClipAsWatched(clipId: string): void {
  if (window.htmx) {
    window.htmx.ajax('POST', `/clip_queue/mark_watched/${clipId}`, {
      target: '#queue-items',
      swap: 'outerHTML'
    });
  }
}

// Show completion message
function showCompletionMessage(): void {
  const playerContainer = document.getElementById('player-container');
  if (playerContainer) {
    playerContainer.innerHTML = `
      <div class="d-flex align-items-center justify-content-center h-100">
        <div class="text-center">
          <h3>All clips watched!</h3>
          <p>No more clips in the queue.</p>
          <button class="btn btn-primary" onclick="location.reload()">Refresh Queue</button>
        </div>
      </div>
    `;
  }
}

// Next clip functionality
export function nextClip(): void {
  if (currentClipId) {
    markClipAsWatched(currentClipId);
    
    if (autoPlayEnabled) {
      setTimeout(() => {
        playNextClip();
      }, 500);
    }
  }
}

// HTMX event handlers
export function initializeHtmxHandlers(): void {
  // Handle player container updates
  document.body.addEventListener('htmx:afterSwap', (event: any) => {
    if (event.detail.target.id === 'player-container') {
      const container = event.detail.target;
      
      if (container.dataset.videoId) {
        // YouTube video
        if (window.YT && window.YT.Player) {
          initializePlayer(container.dataset.videoId, parseInt(container.dataset.startTime || '0'));
        }
      } else if (container.dataset.twitchVideoId) {
        // Twitch video
        initializeTwitchPlayer(container.dataset.twitchVideoId, parseInt(container.dataset.startTime || '0'));
      }
    }
    
    // Handle queue item updates
    if (event.detail.target.id === 'queue-items') {
      // Reapply active styling
      if (currentClipId) {
        const activeItem = document.querySelector(`.queue-item[data-id="${currentClipId}"]`);
        if (activeItem) {
          activeItem.classList.add('active', 'bg-primary-subtle');
        }
      }
      
      // Add click handlers to queue items
      document.querySelectorAll('.queue-item').forEach(item => {
        item.addEventListener('click', (e) => {
          e.preventDefault();
          const clipId = (item as HTMLElement).dataset.id;
          if (clipId) {
            playClip(clipId);
          }
        });
      });
    }
  });
}

// Player cleanup
export function cleanupPlayer(): void {
  if (ytPlayer) {
    ytPlayer.destroy();
    ytPlayer = null;
  }
  isPlayerReady = false;
}

// Make functions globally available
(window as any).playClip = playClip;
(window as any).nextClip = nextClip;
(window as any).markClipAsWatched = markClipAsWatched;
(window as any).toggleAutoplay = toggleAutoplay;

// Initialize everything
document.addEventListener('DOMContentLoaded', () => {
  // Load saved settings
  loadAutoplaySetting();
  
  // Initialize APIs
  initializeYouTubeAPI();
  initializeWebSocket();
  initializeHtmxHandlers();
  
  // Load active clip from localStorage
  const savedClipId = localStorage.getItem('activeQueueItemId');
  if (savedClipId) {
    playClip(savedClipId);
  }
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
  cleanupPlayer();
  if (socket) {
    socket.disconnect();
  }
});