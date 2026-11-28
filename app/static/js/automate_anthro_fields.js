/**
 * Fills the anthropometric results and normalizes the weight, height and blood pressure fields.
 * @returns {void}
 */
(function () {
    "use strict";

    /**
     * Wires the anthropometric and bioimpedance fields once the page is ready.
     * @returns {void}
     */
    function init() {
        /** @type {HTMLInputElement | null} */
        const pesoInput = /** @type {HTMLInputElement | null} */ (document.getElementById("peso"));
        /** @type {HTMLInputElement | null} */
        const alturaInput = /** @type {HTMLInputElement | null} */ (document.getElementById("altura"));
        /** @type {HTMLInputElement | null} */
        const imcInput = /** @type {HTMLInputElement | null} */ (document.getElementById("imc"));
        /** @type {HTMLInputElement | null} */
        const nutriClassInput = /** @type {HTMLInputElement | null} */ (document.getElementById("nutri_class"));
        /** @type {HTMLInputElement | null} */
        const evolucaoInput = /** @type {HTMLInputElement | null} */ (document.getElementById("evolucao"));
        /** @type {HTMLInputElement | null} */
        const pMaxInput = /** @type {HTMLInputElement | null} */ (document.getElementById("p_max"));
        /** @type {HTMLInputElement | null} */
        const pMinInput = /** @type {HTMLInputElement | null} */ (document.getElementById("p_min"));
        /** @type {HTMLInputElement | null} */
        const pIdeInput = /** @type {HTMLInputElement | null} */ (document.getElementById("p_ide"));
        /** @type {HTMLInputElement | null} */
        const paInput = /** @type {HTMLInputElement | null} */ (document.getElementById("pa"));
        /** @type {HTMLElement | null} */
        const paError = document.getElementById("paError");
        /** @type {HTMLInputElement | null} */
        const ingLiqInput = /** @type {HTMLInputElement | null} */ (document.getElementById("ingestao_liquido"));
        /** @type {HTMLInputElement | null} */
        const necCalInput = /** @type {HTMLInputElement | null} */ (document.getElementById("necessidade_calorica"));
        /** @type {HTMLFormElement | null} */
        const form = document.querySelector("form.add-skinfold-form");
        const slimmingKCAL = 30;
        const maintenanceKCAL = 35;
        const gainKCAL = 45;
        const mlWater = 35;

        /** @type {HTMLInputElement | null} */
        let peso_anteriorInput = /** @type {HTMLInputElement | null} */ (document.getElementById("peso_anterior"));
        let peso_anterior = peso_anteriorInput ? parseFloat(peso_anteriorInput.value) : 0;

        if (pesoInput) normalizePeso();
        if (alturaInput) normalizeAltura();
        if (imcInput) calculateIMC();
        if (pesoInput && evolucaoInput) calculateEvolucao();
        if (pesoInput && ingLiqInput) calculateWaterIngestion();
        if (alturaInput && pMinInput && pMaxInput && pIdeInput) recalcWeights();

        /**
         * Replaces the comma of the weight field by a dot while the user types.
         * @this {HTMLInputElement}
         * @returns {void}
         */
        function replaceComma() {
            this.value = this.value.replace(",", ".");
        }

        /**
         * Listens to the weight field so a decimal comma becomes a dot.
         * @returns {void}
         */
        function normalizePeso() {
            pesoInput.addEventListener("input", replaceComma);
        }

        /**
         * Converts a height typed in centimeters to meters.
         * @returns {void}
         */
        function normalizeAltura() {
            if (!alturaInput) return;

            let altura = parseFloat(alturaInput.value);
            if (!isNaN(altura) && altura > 3) {
                altura = altura / 100;
                alturaInput.value = altura.toFixed(2);
            }
        }

        /**
         * Calculates the BMI, its classification and the daily calories, and fills the fields.
         * @returns {void}
         */
        function calculateIMC() {
            if (!imcInput || !pesoInput || !alturaInput) return;

            let peso = parseFloat(pesoInput.value);
            let altura = parseFloat(alturaInput.value);
            if (!isNaN(peso) && !isNaN(altura) && altura > 0) {
                let imc = peso / (altura * altura);
                imcInput.value = imc.toFixed(2);
                calculateNutriClass(imc);

                if (imc > 24.9) {
                    calculateKcalLoseWeight();
                } else if (imc <= 24.9 && imc >= 18.5) {
                    calculateKcalMaintenance();
                } else {
                    calculateKcalGainWeight();
                }
            } else {
                imcInput.value = "";
                if (nutriClassInput) nutriClassInput.value = "";
            }
        }

        /**
         * Sets the nutritional classification that matches a BMI.
         * @param {number} imc Body mass index.
         * @returns {void}
         */
        function calculateNutriClass(imc) {
            if (!nutriClassInput) return;

            let situation = [
                "Abaixo do peso", "Peso normal",
                "Sobrepeso", "Obesidade grau I",
                "Obesidade grau II", "Obesidade grau III"
            ];
            let classification = "";
            if (imc < 18.5) classification = situation[0];
            else if (imc >= 18.5 && imc <= 24.9) classification = situation[1];
            else if (imc > 24.9 && imc <= 29.9) classification = situation[2];
            else if (imc > 29.9 && imc <= 34.9) classification = situation[3];
            else if (imc > 34.9 && imc <= 39.9) classification = situation[4];
            else if (imc > 39.9) classification = situation[5];

            nutriClassInput.value = classification;
        }

        /**
         * Describes the difference between the current and the previous weight.
         * @returns {void}
         */
        function calculateEvolucao() {
            if (!pesoInput || !evolucaoInput) return;

            let peso = parseFloat(pesoInput.value);
            if (isNaN(peso)) {
                evolucaoInput.value = "";
                return;
            }
            let diff = peso - peso_anterior;
            if (diff === peso) {
                evolucaoInput.value = "primeira avaliação";
            } else if (diff > 0) {
                evolucaoInput.value = "ganhou " + diff.toFixed(2) + " kg";
            } else if (diff < 0) {
                evolucaoInput.value = "perdeu " + Math.abs(diff).toFixed(2) + " kg";
            }
        }

        /**
         * Recalculates the maximum, minimum and ideal weights from the height.
         * @returns {void}
         */
        function recalcWeights() {
            if (!alturaInput || !pMaxInput || !pMinInput || !pIdeInput) return;

            let altura = parseFloat(alturaInput.value);
            if (!isNaN(altura) && altura > 0) {
                pMaxInput.value = (25 * (altura ** 2)).toFixed(2);
                pMinInput.value = (18.5 * (altura ** 2)).toFixed(2);
                pIdeInput.value = (21.75 * (altura ** 2)).toFixed(2);
            } else {
                pMaxInput.value = "";
                pMinInput.value = "";
                pIdeInput.value = "";
            }
        }

        /**
         * Fills the daily calories for losing weight.
         * @returns {void}
         */
        function calculateKcalLoseWeight() {
            if (!pesoInput || !necCalInput) return;

            let weight = parseFloat(pesoInput.value);
            if (isNaN(weight)) {
                necCalInput.value = "";
                return;
            }
            let amountKCAL = (weight * slimmingKCAL);
            necCalInput.value = `${Math.round(amountKCAL)} Kcal/ Dia (Emagrecer)`;
        }

        /**
         * Fills the daily calories for maintaining weight.
         * @returns {void}
         */
        function calculateKcalMaintenance() {
            if (!pesoInput || !necCalInput) return;

            let weight = parseFloat(pesoInput.value);
            if (isNaN(weight)) {
                necCalInput.value = "";
                return;
            }
            let amountKCAL = (weight * maintenanceKCAL);
            necCalInput.value = `${Math.round(amountKCAL)} Kcal/ Dia (Manutenção)`;
        }

        /**
         * Fills the daily calories for gaining weight.
         * @returns {void}
         */
        function calculateKcalGainWeight() {
            if (!pesoInput || !necCalInput) return;

            let weight = parseFloat(pesoInput.value);
            if (isNaN(weight)) {
                necCalInput.value = "";
                return;
            }
            let amountKCAL = (weight * gainKCAL);
            necCalInput.value = `${Math.round(amountKCAL)} Kcal/ Dia (Ganhar Peso)`;
        }

        /**
         * Fills the daily water intake in liters.
         * @returns {void}
         */
        function calculateWaterIngestion() {
            if (!pesoInput || !ingLiqInput) return;

            let peso = parseFloat(pesoInput.value);
            if (isNaN(peso)) {
                ingLiqInput.value = "";
                return;
            }
            let amountWater = ((peso * mlWater) / 1000);
            ingLiqInput.value = amountWater;
        }

        /**
         * Validates the blood pressure field and expands short values such as 12/8 to 120/80.
         * @returns {void}
         */
        function normalizePA() {
            if (!paInput || !paError) return;

            paError.textContent = "";
            let paValue = paInput.value.trim();
            if (paValue === "") return;

            let regex = /^\d{1,3}\/\d{1,2}$/;
            if (!regex.test(paValue)) {
                paError.textContent = "Formato inválido. Use até 3 dígitos antes da barra e até 2 dígitos depois (ex: 120/80).";
                paInput.focus();
                return;
            }
            let parts = paValue.split("/");
            let sys = parseInt(parts[0], 10);
            let dia = parseInt(parts[1], 10);

            if (sys < 30) {
                sys *= 10;
            }
            if (dia < 30) {
                dia *= 10;
            }
            paInput.value = sys + "/" + dia;
        }

        /**
         * Validates the blood pressure when the field loses focus.
         * @returns {void}
         */
        function onPaBlur() {
            normalizePA();
        }

        /**
         * Blocks the bioimpedance form when the blood pressure has an invalid format.
         * @param {Event} e Submit event.
         * @returns {void}
         */
        function onSkinfoldSubmit(e) {
            normalizePA();
            if (paError && paError.textContent !== "") {
                e.preventDefault();
                alert("Por favor, corrija o formato da Pressão Arterial (ex: 000/00).");
            }
        }

        if (paInput) {
            paInput.addEventListener("blur", onPaBlur);
        }

        if (form) {
            form.addEventListener("submit", onSkinfoldSubmit);
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
