import type { Chart as ChartType } from 'chart.js';

// Chart.js is loaded globally via vendor.ts
declare const Chart: typeof ChartType;

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
  if (!transcriptionStatsCtx) {
    console.error('Canvas element not found');
    return;
  }
  
  try {
    // Get the current text color from the document
    const textColor = getComputedStyle(document.documentElement).getPropertyValue('--bs-body-color');
    
    const chart = new Chart(transcriptionStatsCtx, {
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
      events: [], // Disable all events
      plugins: {
        legend: { 
          display: true,
          position: 'right',
          align: 'center',
          labels: {
            usePointStyle: true,
            color: textColor,
            generateLabels: function(chart: any) {
              const data = chart.data.datasets[0].data;
              const labels = chart.data.labels;
              const total = data.reduce((sum: number, val: number) => sum + val, 0);
              return labels.map((label: string, index: number) => ({
                text: `${label}: ${data[index]}`,
                fillStyle: chart.data.datasets[0].backgroundColor[index],
                strokeStyle: chart.data.datasets[0].backgroundColor[index],
                fontColor: textColor,
                lineWidth: 1
              }));
            }
          }
        },
        tooltip: { enabled: false }
      }
    }
  });
  } catch (error) {
    console.error('Error creating chart:', error);
  }
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

let mainChart: any = null;

// Initialize main chart
function initializeMainChart(): void {
  const chartDataElement = document.getElementById('chart-data');
  const chartCanvas = document.getElementById('myChart') as HTMLCanvasElement;
  
  if (!chartDataElement || !chartCanvas) {
    console.log('Chart elements not found:', { chartDataElement, chartCanvas });
    return;
  }
  
  // Don't create chart if it already exists
  if (mainChart) {
    return;
  }
  
  try {
    const chartData = JSON.parse(chartDataElement.textContent || '{}');
    
    if (!chartData.labels || !chartData.data) {
      console.log('Invalid chart data structure');
      return;
    }
    
    // Set canvas dimensions explicitly
    chartCanvas.width = chartCanvas.offsetWidth;
    chartCanvas.height = chartCanvas.offsetHeight;
    
    mainChart = new Chart(chartCanvas, {
      type: 'line',
      data: {
        labels: chartData.labels,
        datasets: [{
          label: 'Search Results',
          data: chartData.data,
          borderColor: '#8b5cf6',
          backgroundColor: 'rgba(139, 92, 246, 0.1)',
          tension: 0.1
        }]
      },
      options: {
        events: [], // Disable all events
        plugins: {
          legend: { display: true },
          tooltip: { enabled: false }
        },
        scales: {
          y: {
            beginAtZero: true,
            title: {
              display: true,
              text: 'Number of Results'
            }
          },
          x: {
            title: {
              display: true,
              text: 'Upload Date'
            }
          }
        }
      }
    });
  } catch (e) {
    console.error('Error parsing chart data:', e);
  }
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
  
  // Get transcription stats from canvas data attributes
  const transcriptionStatsCanvas = document.getElementById('transcriptionStatsChart') as HTMLCanvasElement;
  if (transcriptionStatsCanvas) {
    // Match chart height to search form height (accounting for the title paragraph)
    const searchForm = document.querySelector('.search-form');
    const chartContainer = document.getElementById('chartContainer');
    const titleParagraph = document.querySelector('.mb-2');
    if (searchForm && chartContainer && titleParagraph) {
      const searchFormHeight = searchForm.getBoundingClientRect().height;
      const titleHeight = titleParagraph.getBoundingClientRect().height;
      const availableHeight = searchFormHeight - titleHeight;
      chartContainer.style.height = `${availableHeight}px`;
      chartContainer.style.maxHeight = `${availableHeight}px`;
      console.log('Search form height:', searchFormHeight, 'Title height:', titleHeight, 'Chart height:', availableHeight);
    }
    
    const stats: TranscriptionStats = {
      high_quality: parseInt(transcriptionStatsCanvas.dataset.hqCount || '0'),
      low_quality: parseInt(transcriptionStatsCanvas.dataset.lqCount || '0'),
      no_transcription: parseInt(transcriptionStatsCanvas.dataset.noTranscription || '0')
    };
    initializeTranscriptionChart(stats);
  }
  
  // Initialize main chart when collapse is shown
  const chartCollapse = document.getElementById('collapseChart');
  if (chartCollapse) {
    chartCollapse.addEventListener('shown.bs.collapse', () => {
      initializeMainChart();
    });
  }
});