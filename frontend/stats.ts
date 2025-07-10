// Statistics page functionality
declare global {
  interface Window {
    bootstrap: any;
    Chart: any;
  }
}

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
    cutout: '70%',
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: function(context: any) {
            const value = context.raw;
            const total = data.videoCount;
            const percentage = ((value / total) * 100).toFixed(1);
            const formattedValue = new Intl.NumberFormat().format(value);
            return `${context.label}: ${formattedValue} (${percentage}%)`;
          }
        }
      }
    }
  };
  
  new window.Chart(transcriptionQualityCtx, {
    type: "doughnut",
    data: chartData,
    options: chartOptions
  });
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
  // Chart data will be injected from template
  const chartDataElement = document.getElementById('chart-data');
  if (chartDataElement) {
    try {
      const data = JSON.parse(chartDataElement.textContent || '{}');
      initializeStats(data);
    } catch (e) {
      console.error('Error parsing chart data:', e);
    }
  }
});