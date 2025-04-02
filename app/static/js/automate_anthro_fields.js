document.addEventListener("DOMContentLoaded", function () {
    const pesoInput = document.getElementById("peso");
    const alturaInput = document.getElementById("altura");
    const imcInput = document.getElementById("imc");
    const nutriClassInput = document.getElementById("nutri_class");
    const evolucaoInput = document.getElementById("evolucao");
    const pMaxInput = document.getElementById("p_max");
    const pMinInput = document.getElementById("p_min");
    const pIdeInput = document.getElementById("p_ide");
    const paInput = document.getElementById("pa");
    const paError = document.getElementById("paError");
    const ingLiqInput = document.getElementById("ingestao_liquido");
    const necCalInput = document.getElementById("necessidade_calorica");
    const form = document.querySelector("form.add-skinfold-form");
    const slimmingKCAL = 30;
    const maintenanceKCAL = 35;
    const gainKCAL = 45;
    const mlWater = 35;

    // Get the previous weight evaluation (this is a 'hidden' input added on template)
    let peso_anteriorInput = document.getElementById("peso_anterior");
    let peso_anterior = peso_anteriorInput ? parseFloat(peso_anteriorInput.value) : 0;

    if (alturaInput) normalizeAltura();
    if (imcInput) calculateIMC();
    if (pesoInput && evolucaoInput) calculateEvolucao();
    if (pesoInput && ingLiqInput) calculateWaterIngestion();
    if (alturaInput && pMinInput && pMaxInput && pIdeInput) recalcWeights();

    // Ensure height in meters
    function normalizeAltura() {
        if (!alturaInput) return;

        let altura = parseFloat(alturaInput.value);
        if (!isNaN(altura) && altura > 3) {
            altura = altura / 100;
            alturaInput.value = altura.toFixed(2);
        }
    }

    // Calculate BMI and update the field
    function calculateIMC() {
        if (!imcInput) return;

        let peso = parseFloat(pesoInput.value);
        let altura = parseFloat(alturaInput.value);
        if (!isNaN(peso) && !isNaN(altura) && altura > 0) {
            let imc = peso / (altura * altura);
            imcInput.value = imc.toFixed(2);
            calculateNutriClass(imc);

            // Call for Kcal daily need calculation
            if (imc > 24.9) {
                calculateKcalLoseWeight();
            } else if (imc <= 24.9 && imc >= 18.5) {
                calculateKcalMaintenance();
            } else {
                calculateKcalGainWeight();
            }
        } else {
            imcInput.value = "";
            nutriClassInput.value = "";
        }
    }

    // Define nutritional classification based on BMI
    function calculateNutriClass(imc) {
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

    // Calculate evolution (diff between current and previous weight )
    function calculateEvolucao() {
        if (!pesoInput) return;

        let peso = parseFloat(pesoInput.value);
        if (isNaN(peso)) {
            evolucaoInput.value = "";
            return;
        }
        let diff = peso - peso_anterior;
        // If diff is equal to the weight itself, it means that this is the first evaluation
        if (diff === peso) {
            evolucaoInput.value = "primeira avaliação";
        } else if (diff > 0) {
            evolucaoInput.value = "ganhou " + diff.toFixed(2) + " kg";
        } else if (diff < 0) {
            evolucaoInput.value = "perdeu " + Math.abs(diff).toFixed(2) + " kg";
        }
    }

    // Recalculate best weight, min weight and max weight
    function recalcWeights() {
        if (!alturaInput) return;

        let altura = parseFloat(alturaInput.value);
        if (!isNaN(altura) && altura > 0) {
            // Max Weight (IMC == 25)
            pMaxInput.value = (25 * (altura ** 2)).toFixed(2);
            // Min Weight (IMC == 18.5)
            pMinInput.value = (18.5 * (altura ** 2)).toFixed(2);
            // Best Weight (using the average value of 18.5 and 24.9, that is 21.75)
            pIdeInput.value = (21.75 * (altura ** 2)).toFixed(2);
        } else {
            pMaxInput.value = "";
            pMinInput.value = "";
            pIdeInput.value = "";
        }
    }

    // Calculate daily KCAL for losing weight
    function calculateKcalLoseWeight() {
        if (!pesoInput) return;

        let weight = parseFloat(pesoInput.value);
        if (isNaN(weight)) {
            necCalInput.value = "";
            return;
        }
        let amountKCAL = (weight * slimmingKCAL);
        necCalInput.value = `${Math.round(amountKCAL)} Kcal/ Dia (Emagrecer)`;
    };

    // Calculate maintenance of daily KCAL
    function calculateKcalMaintenance() {
        if (!pesoInput) return;

        let weight = parseFloat(pesoInput.value);
        if (isNaN(weight)) {
            necCalInput.value = "";
            return;
        }
        let amountKCAL = (weight * maintenanceKCAL);
        necCalInput.value = `${Math.round(amountKCAL)} Kcal/ Dia (Manutenção)`;
    };

    // Calculate daily KCAL for gain of weight
    function calculateKcalGainWeight() {
        if (!pesoInput) return;

        let weight = parseFloat(pesoInput.value);
        if (isNaN(weight)) {
            necCalInput.value = "";
            return;
        }
        let amountKCAL = (weight * gainKCAL);
        necCalInput.value = `${Math.round(amountKCAL)} Kcal/ Dia (Ganhar Peso)`;
    };

    // Calculate the need of daily water ingestion
    function calculateWaterIngestion() {
        if (!pesoInput) return;

        let peso = parseFloat(pesoInput.value);
        if (isNaN(peso)) {
            ingLiqInput.value = "";
            return;
        }
        let amountWater = ((peso * mlWater) / 1000);
        ingLiqInput.value = amountWater;
    };

    // Function to normalize PA Field
    function normalizePA() {
        if (!paInput) return;

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

    if (paInput) {
        paInput.addEventListener("blur", normalizePA);
    }

    if (form) {
        form.addEventListener("submit", function(e) {
            normalizePA();
            if (paError.textContent !== "") {
                e.preventDefault();
                alert("Por favor, corrija o formato da Pressão Arterial (ex: 000/00).");
            }
        });
    }
});
