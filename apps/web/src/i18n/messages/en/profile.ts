/**
 * @file profile.ts
 * @description profile messages (en mirrors the zh-CN key set exactly).
 */

export const profile = {
  // Page skeleton (PageHead / header button / loading state)
  "page.eyebrow": "Profile",
  "page.title": "Profile",
  "page.loading": "Loading profile…",
  "page.save": "Save profile",
  "page.clear": "Clear profile",

  // Basic info
  "basic.title": "Basic Information",
  "basic.name.label": "Name",
  "basic.gender.label": "Gender",
  "basic.identity.label": "Identity",
  "basic.email.label": "Email",
  "basic.phone.label": "Phone / WeChat",

  // Education
  "education.title": "Education",
  "education.school.label": "School",
  "education.major.label": "Major",
  "education.level.label": "Degree Level",
  "education.graduationYear.label": "Graduation Year",
  "education.english.label": "English Level",

  // Job intent
  "jobIntent.title": "Job Intent",
  "jobIntent.direction.label": "Job Direction",
  "jobIntent.role.label": "Target Role",
  "jobIntent.experience.label": "Years of Experience",
  "jobIntent.experienceDetail.label": "Experience Details",
  "jobIntent.company.label": "Current Company",
  "jobIntent.salary.label": "Expected Salary",
  "jobIntent.city.label": "Current City",
  "jobIntent.expectedCity.label": "Preferred City",
  "jobIntent.noticePeriod.label": "Availability",
  "jobIntent.remote.label": "Open to Remote",

  // Skills & introduction
  "skills.title": "Skills & Introduction",
  "skills.selfIntro.label": "Self Introduction",
  "skills.highlights.label": "Career Highlights",
  "skills.projects.label": "Signature Projects",
  "skills.strengths.label": "Strengths",
  "skills.weaknesses.label": "Areas to Improve",
  "skills.certificates.label": "Certificates",
  "skills.domains.label": "Tech Domains",
  "skills.domains.add": "Add",
  "skills.domains.remove": "Remove",
  "skills.domains.error": "Please fill in at least one tech domain",

  // Online identity
  "online.title": "Online Presence",
  "online.github.label": "GitHub",
  "online.languages.label": "Preferred Languages",
  "online.portfolio.label": "Portfolio / Blog",
  "online.linkedin.label": "LinkedIn",

  // Completion
  "completion.title": "Profile Completion",
  "completion.required": "Required",
  "completion.optional": "Optional",
  "completion.missingList": "Missing required: {labels}",
  "completion.allReady": "All required fields are ready",

  // Preview
  "preview.unnamed": "Unnamed",
  "preview.emptyHint": "Complete your profile to see a preview",
  "preview.major.label": "Major",
  "preview.major.value": "{major} · {year}",
  "preview.degree.label": "Degree",
  "preview.role.label": "Target Role",
  "preview.direction.label": "Job Direction",
  "preview.company.label": "Current Company",
  "preview.expectedCity.label": "Preferred City",
  "preview.city.label": "City",
  "preview.email.label": "Email",
  "preview.phone.label": "Phone/WeChat",
  "preview.github.label": "GitHub",
  "preview.domains.title": "Tech Stack",
  "preview.selfIntro.title": "Self Introduction",

  // Unsaved changes dialog
  "unsaved.title": "Unsaved Changes",
  "unsaved.body": "Unsaved changes will be lost if you leave this page.",
  "unsaved.stay": "Stay on this page",
  "unsaved.leave": "Discard and leave",

  // Clear profile
  "clear.title": "Clear profile",
  "clear.body": "This will erase every field in the current profile. This cannot be undone.",
  "clear.cancel": "Cancel",
  "clear.confirm": "Clear",
  "clear.success": "Cleared",
  "clear.failed": "Clear failed",

  // Save / load status messages
  "save.missingRequired": "Please fill in required fields first: {labels}",
  "save.success": "Saved",
  "save.failed": "Save failed",
  "load.failed": "Load failed",

  // Shared field error
  "field.requiredError": "Please enter {label}",

  // List separator (joins missing required labels)
  "format.listSeparator": ", ",
} as const;

export type ProfileMessageKey = keyof typeof profile;
