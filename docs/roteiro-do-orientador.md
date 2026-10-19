03/09/2025

Etapa 01 – Baixar os dados de Consumo Alimentar do SISVAN

Baixar os relatórios mensais de consumo alimentar do SISVAN

https://sisaps.saude.gov.br/sisvan/relatoriopublico/index

API: https://opendatasus.saude.gov.br/dataset/sisvan-estado-nutricional

Usar 	Web Scrapping (ou Web Automation), Python com Selenium (um clássico) ou Playwright (mais moderno / recente) para interagir com o navegador.

Baixar os relatórios mensais, agrupados por município (todo o Brasil):

de 2015 a 2024

de janeiro a dezembro

Faixa 	etária: 2 anos ou mais

Fases da Vida: “Crianças de 2 a 4 anos” até “Adolescentes”

Todos os tipos de relatórios

Criar um padrão para salvar os arquivos. Sugestão:

uma pasta para cada ano;

criar um padrão de nomes, exemplo: consumo_de_fruta__2a4anos_2015_01

Ao baixar, retirar os cabeçalhos dos arquivos.

Depois de baixar, fazer alguns “testes” por amostragem com relatórios 	baixados manualmente do site.

Unificar as perguntas.

Etapa 02 – Incluir os dados de Estado Nutricional do SISVAN

Etapa 03 – Sumarizar os dados, por ano, cidade e estado.



Etapa 04 – Agregar os dados do PNAE



Dados do PNAE de 2015 a 2024

https://www.gov.br/fnde/pt-br/acesso-a-informacao/acoes-e-programas/programas/pnae/consultas/repasses-financeiros-por-entidade-executora/pnae-repasses-financeiros



Baixar os arquivos com as idades da população residente no município em 2019

http://tabnet.datasus.gov.br/cgi/tabcgi.exe?ibge/cnv/popsvs2024br.def

Preencher os campos do relatório da seguinte forma:

Linha: município

Coluna: idade simples

Conteúdo: população residente

Período disponível: 2019

Baixar por região



Para cada arquivo anual (2a4, 5a9 e adolescentes), incluir as seguintes colunas:

2 a 4

Coluna com valor do PNACN

Coluna com valor do PNAPN

Percentual 2 e 3 (cada município tem o seu percentual)

Percentual 4 (cada município tem o seu percentual)

Valor PNAE (percentuais multiplicados pelos valores PNACN e PNAPN)

5 a 9

Coluna com valor do PNAPN

Coluna com valor do PNAFN e PN+FN

Percentual 5 (cada município tem o seu percentual)

Percentual 6 a 9 (cada município tem o seu percentual)

Valor PNAE (percentuais multiplicados pelos valores PNAPN, PNAFN e PN+FN)



Adolescentes

Baixar os microdados do censo escolar de 2015 a 2024

https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/censo-escolar

Coluna com valor do PNAMN, PNAMI, PN+MN

Coluna com valor do PNAFN e PN+FN

Percentual 10 a 15 (cada município tem o seu percentual)

QT_MAT_FUND, QT_MAT_FUND_AF (quantidade de matrículas de escolas estaduais do município naquele ano)

PERC_QT_MAT_FUND, PERC_QT_MAT_FUND_AF (percentuais em relação ao total de matrículas do estado)

Valor PNAE EF

Valor PNAE AF
