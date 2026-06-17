// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Spanish Castilian (`es`).
class AppLocalizationsEs extends AppLocalizations {
  AppLocalizationsEs([String locale = 'es']) : super(locale);

  @override
  String get online => 'en línea';

  @override
  String get offline => 'sin conexión';

  @override
  String get newConvTooltip =>
      'Nueva conversación · descarta el turno actual y la cola';

  @override
  String get newConvButton => 'Nueva';

  @override
  String get settingsTooltip => 'Opciones';

  @override
  String get newConvDialogTitle => 'Nueva conversación';

  @override
  String get newConvDialogContent =>
      'Se descarta el turno en curso y la cola, y empieza una conversación nueva. ¿Continuar?';

  @override
  String get cancel => 'Cancelar';

  @override
  String get start => 'Empezar';

  @override
  String get clearQueue => 'Borrar cola';

  @override
  String get clearQueueContent =>
      'Se eliminan los turnos en cola. El turno en curso sigue. ¿Continuar?';

  @override
  String get clearQueueConfirm => 'Borrar';

  @override
  String get notifPermHint =>
      'Sin permiso de notificaciones, Mirach no podrá avisarte cuando necesite tu atención mientras estás fuera de la app.';

  @override
  String get openSettings => 'Ajustes';

  @override
  String get settingsHeader => 'OPCIONES';

  @override
  String get autoSendLabel => 'Envío automático de voz';

  @override
  String get showReasoning => 'Mostrar razonamiento';

  @override
  String get showToolCalls => 'Mostrar llamadas a herramientas';

  @override
  String get showToolResults => 'Mostrar resultados de herramientas';

  @override
  String get readResponse => 'Lectura de respuesta';

  @override
  String get ttsModeAuto => 'Auto';

  @override
  String get ttsModeAlways => 'Siempre';

  @override
  String get ttsModeNever => 'Nunca';

  @override
  String get languageLabel => 'Idioma';

  @override
  String get disconnect => 'Desconectar de la PC';

  @override
  String get speakingBanner => 'Leyendo…  Toca para detener';

  @override
  String get reasoningLive => '🧠 trabajando…';

  @override
  String get reasoningDone => '🧠 proceso';

  @override
  String get processing => 'procesando…';

  @override
  String confirmTitle(String name) {
    return '⚠ Confirmar: $name';
  }

  @override
  String confirmTitleResolved(String name) {
    return '⚠ Confirmar: $name (resuelto)';
  }

  @override
  String get confirmApprove => 'Confirmar';

  @override
  String get confirmDeny => 'Denegar';

  @override
  String get toolResultOk => '✓ resultado';

  @override
  String get toolResultError => '✗ error';

  @override
  String get noVoiceDetected => 'No se detectó voz';

  @override
  String get micPermTitle => 'Micrófono';

  @override
  String get micPermContent =>
      'El permiso de micrófono fue denegado permanentemente. Actívalo en Ajustes para usar la entrada por voz.';

  @override
  String get inputHint => 'Escribe un mensaje…';

  @override
  String autoSendCountdown(String seconds) {
    return 'Enviando en ${seconds}s · toca el campo para editar';
  }

  @override
  String get recordingLabel => 'Grabando…';

  @override
  String get transcribingLabel => 'Transcribiendo…';

  @override
  String get send => 'Enviar';

  @override
  String get interrupt => 'Interrumpir';

  @override
  String downloadingModel(String percent) {
    return 'Descargando modelo de voz ($percent%)…';
  }

  @override
  String get loadingModel => 'Cargando modelo de voz…';

  @override
  String get pairingSubtitle =>
      'Escribe la dirección de tu PC y el código de emparejamiento\nque aparece en los logs del daemon.';

  @override
  String get hostLabel => 'Dirección de la PC (host:puerto)';

  @override
  String get codeLabel => 'Código de emparejamiento';

  @override
  String get connectButton => 'Conectar';

  @override
  String pairingFailed(String error) {
    return 'Error de emparejamiento: $error';
  }

  @override
  String get notifWorking => 'Mirach está trabajando…';

  @override
  String get notifTapToReturn => 'Toca para volver';

  @override
  String get notifApprove => 'Aprobar';

  @override
  String get notifDeny => 'Denegar';

  @override
  String get notifStop => 'Parar';

  @override
  String get notifErrorTitle => '⚠ Mirach — error';

  @override
  String get notifInvalidToken =>
      'Token inválido — abre la app para reconectar';

  @override
  String get notifToolFallback => 'herramienta';
}
