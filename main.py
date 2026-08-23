# --- EN LA SECCIÓN DE APROBACIÓN DE PAGO (ADMIN) ---
if accion == "conf":
    for n in user_nums:
        rifa[n]["estado"] = "ocupado"
        rifa[n]["nombre"] = user_nombre
        rifa[n]["user_id"] = user_tel

    del solicitudes[req_id]
    data_rifa["numeros"] = rifa
    data_rifa["solicitudes_pendientes"] = solicitudes

    if all(rifa[str(n)]["estado"] == "ocupado" for n in range(1, 101)):
        data_rifa["estado_rifa"] = "finalizada"

    guardar_data_completa(data_rifa)
    enviar_whatsapp(sender_id, f"✅ *Aprobado.* Números: {nums_formatted}")

    texto_pago_confirmado = (
        f"🎉 *¡Hola {user_nombre}!* 🎉\n\n"
        f"Tu pago fue verificado. Tus números *({nums_formatted})* ya están registrados a tu nombre."
    )

    # 1. Enviar mensaje de confirmación DIRECTO AL PRIVADO DEL USUARIO
    try:
        enviar_whatsapp(user_tel, texto_pago_confirmado)
    except Exception as e:
        print(f"Error enviando confirmación al privado del usuario: {e}")

    # 2. Enviar también al chat de origen (si fue en grupo)
    try:
        if chat_origen != user_tel:
            enviar_whatsapp(chat_origen, texto_pago_confirmado)
    except Exception as e:
        print(f"Error enviando confirmación al chat de origen: {e}")
