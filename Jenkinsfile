// =====================================================================
//  Pipeline de deploy — Vinheria Agnello (ms-pedidos + ms-rastreamento)
// =====================================================================
pipeline {
    agent any

    options {
        skipDefaultCheckout(true)   // o checkout é feito no estágio próprio, abaixo
    }

    environment {
        // Pasta de "produção": volume montado no container do Jenkins (simula o IIS / wwwroot)
        PUBLICACAO = '/publicacao'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
                sh 'git log -1 --oneline'
            }
        }

        stage('Build') {
            steps {
                echo 'Deploy da Vinheria'
                sh '''
                    python3 -m venv .venv
                    . .venv/bin/activate
                    pip install --quiet \
                        -r services/ms-pedidos/requirements.txt \
                        -r services/ms-rastreamento/requirements.txt \
                        pytest bandit
                    python -m py_compile services/ms-pedidos/app.py services/ms-rastreamento/app.py
                    echo "Build OK"
                '''
            }
        }

        stage('Testes') {
            steps {
                sh '. .venv/bin/activate && pytest -v tests'
            }
        }

        stage('DevSecOps') {
            steps {
                // Análise estática de segurança: o build FALHA se houver problema médio ou grave
                sh '. .venv/bin/activate && bandit -r services -ll'
            }
        }

        stage('Deploy') {
            steps {
                sh '''
                    VERSAO="build-$BUILD_NUMBER"
                    DESTINO="$PUBLICACAO/releases/$VERSAO"

                    find services -name __pycache__ -prune -exec rm -rf {} +
                    mkdir -p "$DESTINO"
                    cp -r services/ms-pedidos services/ms-rastreamento "$DESTINO/"
                    printf "versao: %s\\ncommit: %s\\ndata: %s\\n" \
                        "$VERSAO" "$(git rev-parse --short HEAD)" "$(date '+%d/%m/%Y %H:%M:%S')" \
                        > "$DESTINO/VERSAO.txt"

                    # "atual" = o que está no ar (como a pasta do site no IIS)
                    rm -rf "$PUBLICACAO/atual"
                    cp -r "$DESTINO" "$PUBLICACAO/atual"

                    echo "Publicado em $PUBLICACAO/atual"
                    cat "$PUBLICACAO/atual/VERSAO.txt"
                    ls -la "$PUBLICACAO/releases"
                '''
            }
        }
    }

    post {
        success { echo 'Pipeline concluído: Vinheria Agnello publicada.' }
        failure { echo 'Pipeline falhou: nada foi publicado.' }
    }
}
