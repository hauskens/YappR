import { Chart } from "chart.js/auto";
// Search results page functionality
declare global {
  interface Window {
    bootstrap: any;
    $: any; // jQuery
  }
}

interface TranscriptionStats {
  high_quality: number;
  low_quality: number;
  no_transcription: number;
}

// Initialize transcription quality doughnut chart
function initializeTranscriptionChart(stats: TranscriptionStats): void {
  const transcriptionStatsCtx = document.getElementById("transcriptionStatsChart") as HTMLCanvasElement;
  if (!transcriptionStatsCtx) return;
  
  new Chart(transcriptionStatsCtx, {
    type: "doughnut",
    data: {
      labels: ["High Quality", "Low Quality", "No Transcription"],
      datasets: [{
        data: [stats.high_quality, stats.low_quality, stats.no_transcription],
        backgroundColor: [
          "#8b5cf6",
          "#f59e0b", 
          "#64748b"
        ]
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: function(context: any) {
              const value = context.raw;
              const total = stats.high_quality + stats.low_quality + stats.no_transcription;
              const percentage = ((value / total) * 100).toFixed(1);
              return `${context.label}: ${value} (${percentage}%)`;
            }
          }
        }
      }
    }
  });
}

// Initialize clip download form validation
function initializeClipDownloadForms(): void {
  document.querySelectorAll('.clip-download-form').forEach(form => {
    const beforeInput = form.querySelector('input[name="before_seconds"]') as HTMLInputElement;
    const afterInput = form.querySelector('input[name="after_seconds"]') as HTMLInputElement;
    const submitBtn = form.querySelector('.clip-download-btn') as HTMLButtonElement;
    
    if (!beforeInput || !afterInput || !submitBtn) return;
    
    function validateClipForm() {
      const before = parseInt(beforeInput.value) || 0;
      const after = parseInt(afterInput.value) || 0;
      const total = before + after;
      
      if (total > 180) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="bi bi-exclamation-triangle"></i> Too long';
        submitBtn.className = 'btn btn-warning btn-sm clip-download-btn';
      } else if (total === 0) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="bi bi-exclamation-triangle"></i> Too short';
        submitBtn.className = 'btn btn-warning btn-sm clip-download-btn';
      } else {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i class="bi bi-download"></i> Download';
        submitBtn.className = 'btn btn-primary btn-sm clip-download-btn';
      }
    }
    
    beforeInput.addEventListener('input', validateClipForm);
    afterInput.addEventListener('input', validateClipForm);
    validateClipForm();
  });
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
  // Initialize Bootstrap tooltips
  const tooltipTriggerList = Array.from(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
  tooltipTriggerList.forEach(tooltipTriggerEl => {
    new window.bootstrap.Tooltip(tooltipTriggerEl);
  });
  
  // Initialize clip download forms
  initializeClipDownloadForms();
  
  // Chart data will be injected from template
  const transcriptionStatsElement = document.getElementById('transcription-stats-data');
  const chartDataElement = document.getElementById('chart-data');
  
  if (transcriptionStatsElement) {
    try {
      const stats = JSON.parse(transcriptionStatsElement.textContent || '{}');
      initializeTranscriptionChart(stats);
    } catch (e) {
      console.error('Error parsing transcription stats:', e);
    }
  }
  
});