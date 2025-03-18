document.addEventListener("DOMContentLoaded", function() {
    const canvas = document.getElementById('evolutionsChart');
    const evaluationDates = JSON.parse(canvas.getAttribute('data-dates'));
    const evaluationWeights = JSON.parse(canvas.getAttribute('data-weights'));

    const ctx = canvas.getContext('2d');
    const evolutionsChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: evaluationDates,
            datasets: [{
                label: 'Peso (kg)',
                data: evaluationWeights,
                fill: false,
                borderColor: 'rgba(75, 192, 106, 1)',
                backgroundColor: 'rgba(75, 192, 120, 0.5)',
                tension: 0.3
            }]
        },
        options: {
            responsive: true,
            scales: {
                y: {
                    beginAtZero: false,
                    title: {
                        display: true,
                        text: 'Peso (kg)'
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: 'Data Avaliações'
                    }
                }
            }
        }
    });
});
