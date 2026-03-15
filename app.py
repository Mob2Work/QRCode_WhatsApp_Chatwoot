from flask import Flask, render_template, request, jsonify
import requests as http_requests
import base64

app = Flask(__name__)


@app.route("/")
def index():
    webhook_url_param = request.args.get("url", "")
    return render_template("index.html", webhook_url_param=webhook_url_param)


@app.route("/api/get-qrcode", methods=["POST"])
def get_qrcode():
    """
    Recebe a URL do webhook do n8n, dispara a requisição
    e retorna o QR Code em base64.
    """
    data = request.get_json()
    webhook_url = data.get("webhook_url", "").strip()

    if not webhook_url:
        return jsonify({"error": "URL do webhook não informada."}), 400

    try:
        response = http_requests.post(webhook_url, json={}, timeout=30)
        response.raise_for_status()
    except http_requests.exceptions.Timeout:
        return jsonify({"error": "Timeout ao chamar o webhook. Tente novamente."}), 504
    except http_requests.exceptions.ConnectionError:
        return jsonify({"error": "Erro de conexão com o webhook. Verifique a URL."}), 502
    except http_requests.exceptions.HTTPError as e:
        return jsonify({"error": f"Erro HTTP do webhook: {e.response.status_code}"}), 502
    except Exception as e:
        return jsonify({"error": f"Erro inesperado: {str(e)}"}), 500

    # Verifica se a resposta é uma imagem binária direta
    content_type = response.headers.get("Content-Type", "")
    print(f"[DEBUG] Content-Type da resposta: {content_type}")
    print(f"[DEBUG] Status: {response.status_code}, Tamanho: {len(response.content)} bytes")

    if content_type.startswith("image/"):
        # Webhook retornou imagem binária direto (n8n Respond to Webhook com Binary File)
        img_base64 = base64.b64encode(response.content).decode("utf-8")
        data_uri = f"data:{content_type.split(';')[0]};base64,{img_base64}"
        print(f"[DEBUG] Imagem binária recebida, convertida para base64 ({len(img_base64)} chars)")
        return jsonify({"qrcode": data_uri})

    # Tenta extrair o QR Code da resposta JSON
    try:
        resp_data = response.json()
    except ValueError:
        # Tenta usar como texto puro (pode ser base64 direto)
        raw = response.text.strip()
        if "base64" in raw or raw.startswith("iVBOR"):
            return jsonify({"qrcode": raw})
        return jsonify({"error": "Resposta do webhook não é JSON válido."}), 502

    print(f"[DEBUG] Resposta do webhook: {resp_data}")

    # O n8n pode retornar como objeto ou lista
    if isinstance(resp_data, list) and len(resp_data) > 0:
        resp_data = resp_data[0]

    if not isinstance(resp_data, dict):
        return jsonify({
            "error": f"Formato inesperado na resposta: {type(resp_data).__name__}",
        }), 422

    # Busca o campo do QR Code de forma flexível
    qr_code = None

    # 1) Busca por nomes conhecidos (case-insensitive)
    for key, value in resp_data.items():
        if key.lower().replace("_", "").replace("-", "") in ("qrcode", "qr", "qr_code"):
            qr_code = value
            break

    # 2) Se não encontrou, busca qualquer campo que contenha dados base64 de imagem
    if not qr_code:
        for key, value in resp_data.items():
            if isinstance(value, str) and ("base64" in value or value.startswith("iVBOR")):
                qr_code = value
                print(f"[DEBUG] QR Code encontrado no campo '{key}' (por conteúdo base64)")
                break

    if not qr_code:
        # Se não encontrou QR Code, provavelmente o WhatsApp já está conectado
        return jsonify({
            "connected": True,
            "message": "WhatsApp já está conectado e pronto para uso!"
        })

    return jsonify({"qrcode": qr_code})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
