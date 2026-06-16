import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_localizations_en.dart';
import 'app_localizations_es.dart';

// ignore_for_file: type=lint

/// Callers can lookup localized strings with an instance of AppLocalizations
/// returned by `AppLocalizations.of(context)`.
///
/// Applications need to include `AppLocalizations.delegate()` in their app's
/// `localizationDelegates` list, and the locales they support in the app's
/// `supportedLocales` list. For example:
///
/// ```dart
/// import 'l10n/app_localizations.dart';
///
/// return MaterialApp(
///   localizationsDelegates: AppLocalizations.localizationsDelegates,
///   supportedLocales: AppLocalizations.supportedLocales,
///   home: MyApplicationHome(),
/// );
/// ```
///
/// ## Update pubspec.yaml
///
/// Please make sure to update your pubspec.yaml to include the following
/// packages:
///
/// ```yaml
/// dependencies:
///   # Internationalization support.
///   flutter_localizations:
///     sdk: flutter
///   intl: any # Use the pinned version from flutter_localizations
///
///   # Rest of dependencies
/// ```
///
/// ## iOS Applications
///
/// iOS applications define key application metadata, including supported
/// locales, in an Info.plist file that is built into the application bundle.
/// To configure the locales supported by your app, you’ll need to edit this
/// file.
///
/// First, open your project’s ios/Runner.xcworkspace Xcode workspace file.
/// Then, in the Project Navigator, open the Info.plist file under the Runner
/// project’s Runner folder.
///
/// Next, select the Information Property List item, select Add Item from the
/// Editor menu, then select Localizations from the pop-up menu.
///
/// Select and expand the newly-created Localizations item then, for each
/// locale your application supports, add a new item and select the locale
/// you wish to add from the pop-up menu in the Value field. This list should
/// be consistent with the languages listed in the AppLocalizations.supportedLocales
/// property.
abstract class AppLocalizations {
  AppLocalizations(String locale)
    : localeName = intl.Intl.canonicalizedLocale(locale.toString());

  final String localeName;

  static AppLocalizations of(BuildContext context) {
    return Localizations.of<AppLocalizations>(context, AppLocalizations)!;
  }

  static const LocalizationsDelegate<AppLocalizations> delegate =
      _AppLocalizationsDelegate();

  /// A list of this localizations delegate along with the default localizations
  /// delegates.
  ///
  /// Returns a list of localizations delegates containing this delegate along with
  /// GlobalMaterialLocalizations.delegate, GlobalCupertinoLocalizations.delegate,
  /// and GlobalWidgetsLocalizations.delegate.
  ///
  /// Additional delegates can be added by appending to this list in
  /// MaterialApp. This list does not have to be used at all if a custom list
  /// of delegates is preferred or required.
  static const List<LocalizationsDelegate<dynamic>> localizationsDelegates =
      <LocalizationsDelegate<dynamic>>[
        delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
      ];

  /// A list of this localizations delegate's supported locales.
  static const List<Locale> supportedLocales = <Locale>[
    Locale('en'),
    Locale('es'),
  ];

  /// No description provided for @online.
  ///
  /// In en, this message translates to:
  /// **'online'**
  String get online;

  /// No description provided for @offline.
  ///
  /// In en, this message translates to:
  /// **'offline'**
  String get offline;

  /// No description provided for @newConvTooltip.
  ///
  /// In en, this message translates to:
  /// **'New conversation · discards current turn and queue'**
  String get newConvTooltip;

  /// No description provided for @newConvButton.
  ///
  /// In en, this message translates to:
  /// **'New'**
  String get newConvButton;

  /// No description provided for @settingsTooltip.
  ///
  /// In en, this message translates to:
  /// **'Settings'**
  String get settingsTooltip;

  /// No description provided for @newConvDialogTitle.
  ///
  /// In en, this message translates to:
  /// **'New conversation'**
  String get newConvDialogTitle;

  /// No description provided for @newConvDialogContent.
  ///
  /// In en, this message translates to:
  /// **'The current turn and queue will be discarded, and a new conversation will start. Continue?'**
  String get newConvDialogContent;

  /// No description provided for @cancel.
  ///
  /// In en, this message translates to:
  /// **'Cancel'**
  String get cancel;

  /// No description provided for @start.
  ///
  /// In en, this message translates to:
  /// **'Start'**
  String get start;

  /// No description provided for @clearQueue.
  ///
  /// In en, this message translates to:
  /// **'Clear queue'**
  String get clearQueue;

  /// No description provided for @clearQueueContent.
  ///
  /// In en, this message translates to:
  /// **'Queued turns will be removed. The current turn continues. Continue?'**
  String get clearQueueContent;

  /// No description provided for @clearQueueConfirm.
  ///
  /// In en, this message translates to:
  /// **'Clear'**
  String get clearQueueConfirm;

  /// No description provided for @notifPermHint.
  ///
  /// In en, this message translates to:
  /// **'Without notification permission, Mirach won\'t be able to alert you when it needs your attention while the app is in the background.'**
  String get notifPermHint;

  /// No description provided for @openSettings.
  ///
  /// In en, this message translates to:
  /// **'Settings'**
  String get openSettings;

  /// No description provided for @settingsHeader.
  ///
  /// In en, this message translates to:
  /// **'OPTIONS'**
  String get settingsHeader;

  /// No description provided for @autoSendLabel.
  ///
  /// In en, this message translates to:
  /// **'Auto-send voice'**
  String get autoSendLabel;

  /// No description provided for @showReasoning.
  ///
  /// In en, this message translates to:
  /// **'Show reasoning'**
  String get showReasoning;

  /// No description provided for @showToolCalls.
  ///
  /// In en, this message translates to:
  /// **'Show tool calls'**
  String get showToolCalls;

  /// No description provided for @showToolResults.
  ///
  /// In en, this message translates to:
  /// **'Show tool results'**
  String get showToolResults;

  /// No description provided for @readResponse.
  ///
  /// In en, this message translates to:
  /// **'Read response'**
  String get readResponse;

  /// No description provided for @ttsModeAuto.
  ///
  /// In en, this message translates to:
  /// **'Auto'**
  String get ttsModeAuto;

  /// No description provided for @ttsModeAlways.
  ///
  /// In en, this message translates to:
  /// **'Always'**
  String get ttsModeAlways;

  /// No description provided for @ttsModeNever.
  ///
  /// In en, this message translates to:
  /// **'Never'**
  String get ttsModeNever;

  /// No description provided for @languageLabel.
  ///
  /// In en, this message translates to:
  /// **'Language'**
  String get languageLabel;

  /// No description provided for @disconnect.
  ///
  /// In en, this message translates to:
  /// **'Disconnect from PC'**
  String get disconnect;

  /// No description provided for @speakingBanner.
  ///
  /// In en, this message translates to:
  /// **'Reading…  Tap to stop'**
  String get speakingBanner;

  /// No description provided for @reasoningLive.
  ///
  /// In en, this message translates to:
  /// **'🧠 working…'**
  String get reasoningLive;

  /// No description provided for @reasoningDone.
  ///
  /// In en, this message translates to:
  /// **'🧠 process'**
  String get reasoningDone;

  /// No description provided for @processing.
  ///
  /// In en, this message translates to:
  /// **'processing…'**
  String get processing;

  /// No description provided for @confirmTitle.
  ///
  /// In en, this message translates to:
  /// **'⚠ Confirm: {name}'**
  String confirmTitle(String name);

  /// No description provided for @confirmTitleResolved.
  ///
  /// In en, this message translates to:
  /// **'⚠ Confirm: {name} (resolved)'**
  String confirmTitleResolved(String name);

  /// No description provided for @confirmApprove.
  ///
  /// In en, this message translates to:
  /// **'Confirm'**
  String get confirmApprove;

  /// No description provided for @confirmDeny.
  ///
  /// In en, this message translates to:
  /// **'Deny'**
  String get confirmDeny;

  /// No description provided for @toolResultOk.
  ///
  /// In en, this message translates to:
  /// **'✓ result'**
  String get toolResultOk;

  /// No description provided for @toolResultError.
  ///
  /// In en, this message translates to:
  /// **'✗ error'**
  String get toolResultError;

  /// No description provided for @noVoiceDetected.
  ///
  /// In en, this message translates to:
  /// **'No voice detected'**
  String get noVoiceDetected;

  /// No description provided for @micPermTitle.
  ///
  /// In en, this message translates to:
  /// **'Microphone'**
  String get micPermTitle;

  /// No description provided for @micPermContent.
  ///
  /// In en, this message translates to:
  /// **'Microphone permission was permanently denied. Enable it in Settings to use voice input.'**
  String get micPermContent;

  /// No description provided for @inputHint.
  ///
  /// In en, this message translates to:
  /// **'Type a message…'**
  String get inputHint;

  /// No description provided for @autoSendCountdown.
  ///
  /// In en, this message translates to:
  /// **'Sending in {seconds}s · tap the field to edit'**
  String autoSendCountdown(String seconds);

  /// No description provided for @recordingLabel.
  ///
  /// In en, this message translates to:
  /// **'Recording…'**
  String get recordingLabel;

  /// No description provided for @transcribingLabel.
  ///
  /// In en, this message translates to:
  /// **'Transcribing…'**
  String get transcribingLabel;

  /// No description provided for @send.
  ///
  /// In en, this message translates to:
  /// **'Send'**
  String get send;

  /// No description provided for @interrupt.
  ///
  /// In en, this message translates to:
  /// **'Interrupt'**
  String get interrupt;

  /// No description provided for @downloadingModel.
  ///
  /// In en, this message translates to:
  /// **'Downloading voice model ({percent}%)…'**
  String downloadingModel(String percent);

  /// No description provided for @loadingModel.
  ///
  /// In en, this message translates to:
  /// **'Loading voice model…'**
  String get loadingModel;

  /// No description provided for @pairingSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Enter your PC\'s address and the pairing code\nshown in the daemon logs.'**
  String get pairingSubtitle;

  /// No description provided for @hostLabel.
  ///
  /// In en, this message translates to:
  /// **'PC address (host:port)'**
  String get hostLabel;

  /// No description provided for @codeLabel.
  ///
  /// In en, this message translates to:
  /// **'Pairing code'**
  String get codeLabel;

  /// No description provided for @connectButton.
  ///
  /// In en, this message translates to:
  /// **'Connect'**
  String get connectButton;

  /// No description provided for @pairingFailed.
  ///
  /// In en, this message translates to:
  /// **'Pairing failed: {error}'**
  String pairingFailed(String error);
}

class _AppLocalizationsDelegate
    extends LocalizationsDelegate<AppLocalizations> {
  const _AppLocalizationsDelegate();

  @override
  Future<AppLocalizations> load(Locale locale) {
    return SynchronousFuture<AppLocalizations>(lookupAppLocalizations(locale));
  }

  @override
  bool isSupported(Locale locale) =>
      <String>['en', 'es'].contains(locale.languageCode);

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}

AppLocalizations lookupAppLocalizations(Locale locale) {
  // Lookup logic when only language code is specified.
  switch (locale.languageCode) {
    case 'en':
      return AppLocalizationsEn();
    case 'es':
      return AppLocalizationsEs();
  }

  throw FlutterError(
    'AppLocalizations.delegate failed to load unsupported locale "$locale". This is likely '
    'an issue with the localizations generation tool. Please file an issue '
    'on GitHub with a reproducible sample app and the gen-l10n configuration '
    'that was used.',
  );
}
