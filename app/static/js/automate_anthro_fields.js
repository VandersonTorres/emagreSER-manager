document.addEventListener("DOMContentLoaded", function () {
    var pesoInput = document.getElementById("peso");
    var alturaInput = document.getElementById("altura");
    var imcInput = document.getElementById("imc");
    var nutriClassInput = document.getElementById("nutri_class");
    var evolucaoInput = document.getElementById("evolucao");
    var pMaxInput = document.getElementById("p_max");
    var pMinInput = document.getElementById("p_min");
    var pIdeInput = document.getElementById("p_ide");

    // Get the previous weight evaluation (this is a 'hidden' input added on template)
    var peso_anteriorInput = document.getElementById("peso_anterior");
    var peso_anterior = peso_anteriorInput ? parseFloat(peso_anteriorInput.value) : 0;

    // Ensure height in meters
    function normalizeAltura() {
        var altura = parseFloat(alturaInput.value);
        if (!isNaN(altura) && altura > 3) {
            altura = altura / 100;
            alturaInput.value = altura.toFixed(2);
        }
    }

    // Calculate BMI and update the field
    function calculateIMC() {
        var peso = parseFloat(pesoInput.value);
        var altura = parseFloat(alturaInput.value);
        if (!isNaN(peso) && !isNaN(altura) && altura > 0) {
            var imc = peso / (altura * altura);
            imcInput.value = imc.toFixed(2);
            calculateNutriClass(imc);
        } else {
            imcInput.value = "";
            nutriClassInput.value = "";
        }
    }

    // Define nutritional classification based on BMI
    function calculateNutriClass(imc) {
        var situation = [
            "Abaixo do peso", "Peso normal",
            "Sobrepeso", "Obesidade grau I",
            "Obesidade grau II", "Obesidade grau III"
        ];
        var classification = "";
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
        var peso = parseFloat(pesoInput.value);
        if (isNaN(peso)) {
            evolucaoInput.value = "";
            return;
        }
        var diff = peso - peso_anterior;
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
        var altura = parseFloat(alturaInput.value);
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

    // Update the values while user is typing
    pesoInput.addEventListener("input", function () {
        calculateIMC();
        calculateEvolucao();
    });

    alturaInput.addEventListener("blur", function () {
        normalizeAltura();
        calculateIMC();
        recalcWeights();
    });
});
