// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class AppLocalizationsEn extends AppLocalizations {
  AppLocalizationsEn([String locale = 'en']) : super(locale);

  @override
  String get online => 'online';

  @override
  String get offline => 'offline';

  @override
  String get newConvTooltip =>
      'New conversation · discards current turn and queue';

  @override
  String get newConvButton => 'New';

  @override
  String get settingsTooltip => 'Settings';

  @override
  String get newConvDialogTitle => 'New conversation';

  @override
  String get newConvDialogContent =>
      'The current turn and queue will be discarded, and a new conversation will start. Continue?';

  @override
  String get cancel => 'Cancel';

  @override
  String get start => 'Start';

  @override
  String get clearQueue => 'Clear queue';

  @override
  String get clearQueueContent =>
      'Queued turns will be removed. The current turn continues. Continue?';

  @override
  String get clearQueueConfirm => 'Clear';

  @override
  String get notifPermHint =>
      'Without notification permission, Mirach won\'t be able to alert you when it needs your attention while the app is in the background.';

  @override
  String get openSettings => 'Settings';

  @override
  String get settingsHeader => 'OPTIONS';

  @override
  String get autoSendLabel => 'Auto-send voice';

  @override
  String get showReasoning => 'Show reasoning';

  @override
  String get showToolCalls => 'Show tool calls';

  @override
  String get showToolResults => 'Show tool results';

  @override
  String get readResponse => 'Read response';

  @override
  String get ttsModeAuto => 'Auto';

  @override
  String get ttsModeAlways => 'Always';

  @override
  String get ttsModeNever => 'Never';

  @override
  String get languageLabel => 'Language';

  @override
  String get disconnect => 'Disconnect from PC';

  @override
  String get speakingBanner => 'Reading…  Tap to stop';

  @override
  String get reasoningLive => '🧠 working…';

  @override
  String get reasoningDone => '🧠 process';

  @override
  String get processing => 'processing…';

  @override
  String confirmTitle(String name) {
    return '⚠ Confirm: $name';
  }

  @override
  String confirmTitleResolved(String name) {
    return '⚠ Confirm: $name (resolved)';
  }

  @override
  String get confirmApprove => 'Confirm';

  @override
  String get confirmDeny => 'Deny';

  @override
  String get toolResultOk => '✓ result';

  @override
  String get toolResultError => '✗ error';

  @override
  String get noVoiceDetected => 'No voice detected';

  @override
  String get micPermTitle => 'Microphone';

  @override
  String get micPermContent =>
      'Microphone permission was permanently denied. Enable it in Settings to use voice input.';

  @override
  String get inputHint => 'Type a message…';

  @override
  String autoSendCountdown(String seconds) {
    return 'Sending in ${seconds}s · tap the field to edit';
  }

  @override
  String get recordingLabel => 'Recording…';

  @override
  String get transcribingLabel => 'Transcribing…';

  @override
  String get send => 'Send';

  @override
  String get interrupt => 'Interrupt';

  @override
  String downloadingModel(String percent) {
    return 'Downloading voice model ($percent%)…';
  }

  @override
  String get loadingModel => 'Loading voice model…';

  @override
  String get pairingSubtitle =>
      'Enter your PC\'s address and the pairing code\nshown in the daemon logs.';

  @override
  String get hostLabel => 'PC address (host:port)';

  @override
  String get codeLabel => 'Pairing code';

  @override
  String get connectButton => 'Connect';

  @override
  String pairingFailed(String error) {
    return 'Pairing failed: $error';
  }
}
