# Cómo cambiar el modelo de Whisper

## Modelos disponibles

| Modelo | Tamaño | VRAM (int8) | Velocidad | Notas |
|---|---|---|---|---|
| `medium` | 1.5 GB | ~700 MB | ~0.5s | Multilingüe, por defecto recomendado |
| `medium.en` | 1.5 GB | ~700 MB | ~0.5s | Optimizado para inglés, ligeramente mejor en inglés |
| `large-v3-turbo` | 1.6 GB | ~2.3 GB (float16) | ~0.3s | El más rápido pero más VRAM |
| `small` | 466 MB | ~300 MB | ~0.8s | Poca VRAM, menor precisión |

## Cambia el modelo

Edita tu servicio de systemd:

```bash
systemctl --user edit mirach
```

Añade:

```ini
[Service]
Environment=MIRACH_WHISPER_MODEL=medium.en
Environment=MIRACH_WHISPER_COMPUTE=int8
```

Reinicia:

```bash
systemctl --user restart mirach
```

El modelo se descarga automáticamente en el primer uso.

## Tipo de cómputo

| Cómputo | Dispositivo | VRAM | Precisión |
|---|---|---|---|
| `int8` | cuda o cpu | Baja | Buena para voz |
| `float16` | solo cuda | Alta | Máxima precisión |
| `int8_float16` | solo cuda | Media | Enfoque híbrido |

Para la mayoría de usuarios, `int8` en `cuda` es el mejor balance.
