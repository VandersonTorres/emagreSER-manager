"""What the custom history page shows for each case of tests/history_cases.py, read from the page.

The values were recorded from the page as it was before patients without bioimpedance were supported, with the same
reader and the same cases, so a patient with evaluations and measurements must keep showing exactly these values and
texts.
"""

from typing import Any

HISTORY_RECORDED: dict[str, dict[str, Any]] = {
    "single_evaluation": {
        "content": "Voltar Histórico personalizado Paciente Historico single_evaluation Imprimir "
        "histórico Paciente Nome Paciente Historico single_evaluation CPF 000.000.000-21 "
        "Idade 34 1ª avaliação física 10/05/2026 Profissional Profissional Teste 2 - "
        "prof2@test.local Detalhamento IMC atual 24.2 Altura 1.7 Percentual de gordura "
        "25.0% Percentual de massa magra 30.0% Peso inicial 70.0 Peso atual 70.0 Peso "
        "ideal 62.0 Resultado final Paciente ainda está na primeira avaliação Histórico de "
        "evoluções Muito bom! Seu peso máximo é 80.0kg e você está com 70.0kg.",
        "dates": ["10/05/2026"],
        "details": [
            ["IMC atual", "24.2"],
            ["Altura", "1.7"],
            ["Percentual de gordura", "25.0%"],
            ["Percentual de massa magra", "30.0%"],
            ["Peso inicial", "70.0"],
            ["Peso atual", "70.0"],
            ["Peso ideal", "62.0"],
            ["Resultado final", "Paciente ainda está na primeira avaliação"],
        ],
        "heading": "Histórico personalizado",
        "message": "Muito bom! Seu peso máximo é 80.0kg e você está com 70.0kg.",
        "subtitle": "Paciente Historico single_evaluation",
        "summary": [
            ["Nome", "Paciente Historico single_evaluation"],
            ["CPF", "000.000.000-21"],
            ["Idade", "34"],
            ["1ª avaliação física", "10/05/2026"],
            ["Profissional", "Profissional Teste 2 - prof2@test.local"],
        ],
        "title": "Histórico personalizado · EmagreSER",
        "weights": [70.0],
    },
    "gain": {
        "content": "Voltar Histórico personalizado Paciente Historico gain Imprimir histórico Paciente Nome "
        "Paciente Historico gain CPF 000.000.000-22 Idade 41 1ª avaliação física 10/01/2026 "
        "Profissional Profissional Teste 2 - prof2@test.local Detalhamento IMC atual 23.8 Altura 1.62 "
        "Percentual de gordura 25.0% Percentual de massa magra 28.0% Peso inicial 62.5 Peso atual 66.75 "
        "Peso ideal 61.25 Resultado final Ganho de 4.25 Kg Histórico de evoluções Muito bom! Seu peso "
        "máximo é 74.5kg e você está com 66.75kg.",
        "dates": ["10/01/2026", "10/03/2026", "10/05/2026"],
        "details": [
            ["IMC atual", "23.8"],
            ["Altura", "1.62"],
            ["Percentual de gordura", "25.0%"],
            ["Percentual de massa magra", "28.0%"],
            ["Peso inicial", "62.5"],
            ["Peso atual", "66.75"],
            ["Peso ideal", "61.25"],
            ["Resultado final", "Ganho de 4.25 Kg"],
        ],
        "heading": "Histórico personalizado",
        "message": "Muito bom! Seu peso máximo é 74.5kg e você está com 66.75kg.",
        "subtitle": "Paciente Historico gain",
        "summary": [
            ["Nome", "Paciente Historico gain"],
            ["CPF", "000.000.000-22"],
            ["Idade", "41"],
            ["1ª avaliação física", "10/01/2026"],
            ["Profissional", "Profissional Teste 2 - prof2@test.local"],
        ],
        "title": "Histórico personalizado · EmagreSER",
        "weights": [62.5, 64.0, 66.75],
    },
    "loss": {
        "content": "Voltar Histórico personalizado Paciente Historico loss Imprimir histórico Paciente Nome "
        "Paciente Historico loss CPF 000.000.000-23 Idade 52 1ª avaliação física 01/02/2026 "
        "Profissional Profissional Teste 2 - prof2@test.local Detalhamento IMC atual 29.4 Altura 1.68 "
        "Percentual de gordura 33.0% Percentual de massa magra 39.5% Peso inicial 90.0 Peso atual 80.1 "
        "Peso ideal 68.0 Resultado final Perda de 9.9 Kg Histórico de evoluções Força! Mantenha o foco! "
        "Seu peso máximo é 78.0kg e você está com 80.1kg.",
        "dates": ["01/02/2026", "01/03/2026", "01/04/2026", "01/05/2026"],
        "details": [
            ["IMC atual", "29.4"],
            ["Altura", "1.68"],
            ["Percentual de gordura", "33.0%"],
            ["Percentual de massa magra", "39.5%"],
            ["Peso inicial", "90.0"],
            ["Peso atual", "80.1"],
            ["Peso ideal", "68.0"],
            ["Resultado final", "Perda de 9.9 Kg"],
        ],
        "heading": "Histórico personalizado",
        "message": "Força! Mantenha o foco! Seu peso máximo é 78.0kg e você está com 80.1kg.",
        "subtitle": "Paciente Historico loss",
        "summary": [
            ["Nome", "Paciente Historico loss"],
            ["CPF", "000.000.000-23"],
            ["Idade", "52"],
            ["1ª avaliação física", "01/02/2026"],
            ["Profissional", "Profissional Teste 2 - prof2@test.local"],
        ],
        "title": "Histórico personalizado · EmagreSER",
        "weights": [90.0, 86.5, 83.25, 80.1],
    },
    "unchanged": {
        "content": "Voltar Histórico personalizado Paciente Historico unchanged Imprimir histórico Paciente "
        "Nome Paciente Historico unchanged CPF 000.000.000-24 Idade 29 1ª avaliação física "
        "05/03/2026 Profissional Profissional Teste 2 - prof2@test.local Detalhamento IMC atual "
        "22.0 Altura 1.65 Percentual de gordura Ainda não houve registro do índice de gordura "
        "Percentual de massa magra Ainda não houve registro do índice de massa magra Peso inicial "
        "70.0 Peso atual 70.0 Peso ideal 58.0 Resultado final Manutenção do peso inicial: 70.0 Kg "
        "Histórico de evoluções Força! Mantenha o foco! Seu peso máximo é 66.0kg e você está com "
        "70.0kg.",
        "dates": ["05/03/2026", "05/06/2026"],
        "details": [
            ["IMC atual", "22.0"],
            ["Altura", "1.65"],
            ["Percentual de gordura", "Ainda não houve registro do índice de gordura"],
            ["Percentual de massa magra", "Ainda não houve registro do índice de massa magra"],
            ["Peso inicial", "70.0"],
            ["Peso atual", "70.0"],
            ["Peso ideal", "58.0"],
            ["Resultado final", "Manutenção do peso inicial: 70.0 Kg"],
        ],
        "heading": "Histórico personalizado",
        "message": "Força! Mantenha o foco! Seu peso máximo é 66.0kg e você está com 70.0kg.",
        "subtitle": "Paciente Historico unchanged",
        "summary": [
            ["Nome", "Paciente Historico unchanged"],
            ["CPF", "000.000.000-24"],
            ["Idade", "29"],
            ["1ª avaliação física", "05/03/2026"],
            ["Profissional", "Profissional Teste 2 - prof2@test.local"],
        ],
        "title": "Histórico personalizado · EmagreSER",
        "weights": [70.0, 70.0],
    },
    "out_of_order": {
        "content": "Voltar Histórico personalizado Paciente Historico out_of_order Imprimir histórico "
        "Paciente Nome Paciente Historico out_of_order CPF Não informado Idade 33 1ª avaliação "
        "física 01/07/2026 Detalhamento IMC atual 25.1 Altura 1.75 Percentual de gordura Ainda "
        "não houve registro do índice de gordura Percentual de massa magra 35.0% Peso inicial "
        "81.5 Peso atual 78.0 Peso ideal 64.0 Resultado final Perda de 3.5 Kg Histórico de "
        "evoluções Muito bom! Seu peso máximo é 82.0kg e você está com 78.0kg.",
        "dates": ["01/07/2026", "01/08/2026", "01/09/2026"],
        "details": [
            ["IMC atual", "25.1"],
            ["Altura", "1.75"],
            ["Percentual de gordura", "Ainda não houve registro do índice de gordura"],
            ["Percentual de massa magra", "35.0%"],
            ["Peso inicial", "81.5"],
            ["Peso atual", "78.0"],
            ["Peso ideal", "64.0"],
            ["Resultado final", "Perda de 3.5 Kg"],
        ],
        "heading": "Histórico personalizado",
        "message": "Muito bom! Seu peso máximo é 82.0kg e você está com 78.0kg.",
        "subtitle": "Paciente Historico out_of_order",
        "summary": [
            ["Nome", "Paciente Historico out_of_order"],
            ["CPF", "Não informado"],
            ["Idade", "33"],
            ["1ª avaliação física", "01/07/2026"],
        ],
        "title": "Histórico personalizado · EmagreSER",
        "weights": [81.5, 79.9, 78.0],
    },
    "at_maximum_weight": {
        "content": "Voltar Histórico personalizado Paciente Historico at_maximum_weight Imprimir "
        "histórico Paciente Nome Paciente Historico at_maximum_weight CPF 000.000.000-26 "
        "Idade 45 1ª avaliação física 20/05/2026 Profissional Profissional Teste 2 - "
        "prof2@test.local Detalhamento IMC atual 27.5 Altura 1.66 Percentual de gordura "
        "31.2% Percentual de massa magra 33.3% Peso inicial 75.5 Peso atual 75.5 Peso "
        "ideal 63.0 Resultado final Paciente ainda está na primeira avaliação Histórico de "
        "evoluções Força! Mantenha o foco! Seu peso máximo é 75.5kg e você está com "
        "75.5kg.",
        "dates": ["20/05/2026"],
        "details": [
            ["IMC atual", "27.5"],
            ["Altura", "1.66"],
            ["Percentual de gordura", "31.2%"],
            ["Percentual de massa magra", "33.3%"],
            ["Peso inicial", "75.5"],
            ["Peso atual", "75.5"],
            ["Peso ideal", "63.0"],
            ["Resultado final", "Paciente ainda está na primeira avaliação"],
        ],
        "heading": "Histórico personalizado",
        "message": "Força! Mantenha o foco! Seu peso máximo é 75.5kg e você está com 75.5kg.",
        "subtitle": "Paciente Historico at_maximum_weight",
        "summary": [
            ["Nome", "Paciente Historico at_maximum_weight"],
            ["CPF", "000.000.000-26"],
            ["Idade", "45"],
            ["1ª avaliação física", "20/05/2026"],
            ["Profissional", "Profissional Teste 2 - prof2@test.local"],
        ],
        "title": "Histórico personalizado · EmagreSER",
        "weights": [75.5],
    },
}
