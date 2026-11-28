/**
 * Draws the weight charts of the patient pages and wires the print buttons.
 * @returns {void}
 */
(function () {
    "use strict";

    /**
     * Reads a color token of the stylesheet.
     * @param {string} name Custom property name, such as "--app-primary".
     * @param {string} fallback Color used when the property is not defined.
     * @returns {string} The color.
     */
    function readColor(name, fallback) {
        const value = window.getComputedStyle(document.documentElement).getPropertyValue(name).trim();
        return value || fallback;
    }

    /**
     * Parses a JSON list stored in a data attribute of the canvas.
     * @param {HTMLCanvasElement} canvas Canvas that carries the data.
     * @param {string} attribute Attribute name, such as "data-weights".
     * @returns {Array<string | number>} The list, or an empty list when the attribute is missing or invalid.
     */
    function readSeries(canvas, attribute) {
        try {
            const parsed = JSON.parse(canvas.getAttribute(attribute) || "[]");
            return Array.isArray(parsed) ? parsed : [];
        } catch (error) {
            return [];
        }
    }

    /**
     * Draws the weight chart of a canvas that carries data-dates and data-weights.
     * @param {HTMLCanvasElement} canvas Canvas to draw on.
     * @returns {void}
     */
    function drawWeightChart(canvas) {
        const context = canvas.getContext("2d");
        if (!context || !window.Chart) {
            return;
        }
        const primary = readColor("--app-primary", "#29461a");
        const accent = readColor("--app-accent", "#7ec330");
        const muted = readColor("--app-muted", "#5a6655");
        const border = readColor("--app-border", "#e1e6dc");

        new window.Chart(context, {
            type: "line",
            data: {
                labels: readSeries(canvas, "data-dates"),
                datasets: [
                    {
                        label: "Peso (kg)",
                        data: readSeries(canvas, "data-weights"),
                        fill: false,
                        borderColor: primary,
                        backgroundColor: accent,
                        pointBackgroundColor: accent,
                        pointBorderColor: primary,
                        pointRadius: 4,
                        pointHoverRadius: 6,
                        tension: 0.3,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { labels: { color: muted } } },
                scales: {
                    y: {
                        beginAtZero: false,
                        title: { display: true, text: "Peso (kg)", color: muted },
                        ticks: { color: muted },
                        grid: { color: border },
                    },
                    x: {
                        title: { display: true, text: "Data das medições", color: muted },
                        ticks: { color: muted, maxRotation: 45, autoSkip: true },
                        grid: { color: border },
                    },
                },
            },
        });
    }

    /**
     * Opens the print dialog of the browser.
     * @returns {void}
     */
    function printPage() {
        window.print();
    }

    /**
     * Draws every weight chart of the page and wires the print buttons.
     * @returns {void}
     */
    function init() {
        for (const canvas of document.querySelectorAll("canvas[data-dates][data-weights]")) {
            drawWeightChart(/** @type {HTMLCanvasElement} */ (canvas));
        }
        for (const button of document.querySelectorAll("button[data-print]")) {
            button.addEventListener("click", printPage);
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
