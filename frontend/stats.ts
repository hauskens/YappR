import type { Chart as ChartType } from 'chart.js';

// Chart.js is loaded globally via vendor.ts
declare const Chart: typeof ChartType;

interface ChartData {
  transcriptionsHqCount: number;
  transcriptionsLqCount: number;
  videoCount: number;
}

function initializeStats(data: ChartData): void {
  // Initialize tooltips
  const tooltipTriggerList = Array.from(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
  tooltipTriggerList.forEach(tooltipTriggerEl => {
    new window.bootstrap.Tooltip(tooltipTriggerEl);
  });
  
  // Initialize transcription quality doughnut chart
  const transcriptionQualityCtx = document.getElementById("transcriptionQualityChart") as HTMLCanvasElement;
  if (!transcriptionQualityCtx) return;
  
  const chartData = {
    labels: ["High Quality", "Low Quality", "Missing Transcription"],
    datasets: [{
      data: [
        data.transcriptionsHqCount, 
        data.transcriptionsLqCount, 
        data.videoCount - (data.transcriptionsHqCount + data.transcriptionsLqCount)
      ],
      backgroundColor: [
        "#8b5cf6",  // High - Light purple
        "#f59e0b",  // Low - Amber
        "#d1d5db"   // Missing - Light gray
      ],
      borderWidth: 0
    }]
  };
  
  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    events: [], // Disable all events to prevent recursion
    cutout: '70%',
    plugins: {
      legend: { display: false },
      tooltip: { enabled: false }
    }
  };
  
  new Chart(transcriptionQualityCtx, {
    type: "doughnut",
    data: chartData,
    options: chartOptions
  });
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
  // Get chart data from canvas data attributes
  const canvas = document.getElementById('transcriptionQualityChart') as HTMLCanvasElement;
  if (canvas) {
    const data: ChartData = {
      transcriptionsHqCount: parseInt(canvas.dataset.hqCount || '0'),
      transcriptionsLqCount: parseInt(canvas.dataset.lqCount || '0'),
      videoCount: parseInt(canvas.dataset.totalCount || '0')
    };
    initializeStats(data);
  }
});