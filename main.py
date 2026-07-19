# 🏆 DETECTAR GANADOR AUTOMÁTICAMENTE
    elif comando.startswith("resultado de florida con"):
        # ⚠️ REEMPLAZA ESTO con el ID real de tu grupo de WhatsApp (ejemplo: "12036323456789@g.us")
        GRUPO_CHAT_ID = "TU_ID_DE_GRUPO_AQUI@g.us" 

        # Extraemos solo los dígitos numéricos que escribiste al final de la frase
        numeros_encontrados = re.findall(r'\d+', comando)
        if numeros_encontrados:
            num_ganador = str(int(numeros_encontrados[0])) # Lo pasa a entero y luego a string para quitar ceros extras (ej: "07" -> "7")
            
            if num_ganador in rifa:
                info_ganador = rifa[num_ganador]
                
                if info_ganador["estado"] == "ocupado":
                    nombre_ganador = info_ganador["nombre"]
                    telefono_ganador = info_ganador["telefono"].replace("+", "").strip()
                    chat_privado_ganador = f"{telefono_ganador}@c.us"
                    
                    # 1. Armamos el anuncio transparente para el GRUPO
                    texto_grupo = (
                        f"🎉🎉 *¡TENEMOS UN GANADOR EN LA RIFA!* 🎉🎉\n\n"
                        f"El número premiado en el tiro de la Florida fue el *{num_ganador.zfill(2)}*.\n\n"
                        f"🥇 *¡Felicidades {nombre_ganador}!* (@{telefono_ganador}) Eres el ganador de los *400 reales* 💵✨.\n\n"
                        f"📩 Le hemos enviado un mensaje privado automáticamente para coordinar su premio."
                    )
                    lista_menciones = [chat_privado_ganador]
                    
                    # ENVIAR AL GRUPO (Transparencia)
                    enviar_mensaje_whapi(GRUPO_CHAT_ID, texto_grupo, menciones=lista_menciones)
                    
                    # 2. Enviamos el mensaje al PRIVADO del ganador de forma automática
                    texto_privado = (
                        f"¡Hola {nombre_ganador}! 👋\n\n"
                        f"🎉 *¡MUCHAS FELICIDADES!* 🎉\n\n"
                        f"Tu número *{num_ganador.zfill(2)}* salió premiado en el resultado de la Florida y has ganado los *400 reales* de la rifa. 🏆💵\n\n"
                        f"👉 Por favor, ponte en contacto con el administrador lo antes posible para coordinar tu pago (ya sea transferencia PIX aquí en Brasil o entrega en Cuba en CUP)."
                    )
                    enviar_mensaje_whapi(chat_privado_ganador, texto_privado)
                    
                    # Evitamos que se duplique el mensaje al final del webhook
                    respuesta = "" 
                else:
                    respuesta = f"🎫 El número *{num_ganador.zfill(2)}* salió premiado en la Florida, pero lamentablemente quedó *Disponible* (nadie lo compró)."
            else:
                respuesta = "⚠️ El número ingresado no está en el rango correcto (debe ser del 1 al 100)."
        else:
            respuesta = "⚠️ Por favor, escribe el número ganador al final de la frase. Ejemplo: *resultado de florida con 25*"
