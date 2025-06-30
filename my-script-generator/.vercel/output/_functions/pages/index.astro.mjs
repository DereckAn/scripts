import { b as createAstro, c as createComponent, e as addAttribute, f as renderHead, g as renderComponent, r as renderTemplate } from '../chunks/astro/server_DJgDqttu.mjs';
import 'kleur/colors';
/* empty css                                 */
import { jsxs, jsx, Fragment } from 'react/jsx-runtime';
import React, { useState } from 'react';
import { S as ScriptGenerator$1 } from '../chunks/scriptGenerator_EUkB3Ipc.mjs';
export { renderers } from '../renderers.mjs';

function PlatformStep({ formState, onUpdate, onNext }) {
  const platforms = [
    {
      id: "windows",
      name: "Windows",
      icon: "🪟",
      description: "Windows 10/11 with winget package manager",
      color: "bg-blue-50 border-blue-200 hover:bg-blue-100"
    },
    {
      id: "macos",
      name: "macOS",
      icon: "🍎",
      description: "macOS with Homebrew package manager",
      color: "bg-gray-50 border-gray-200 hover:bg-gray-100"
    },
    {
      id: "linux",
      name: "Linux",
      icon: "🐧",
      description: "Various Linux distributions",
      color: "bg-orange-50 border-orange-200 hover:bg-orange-100"
    }
  ];
  const handlePlatformSelect = (platform) => {
    onUpdate({ platform });
  };
  return /* @__PURE__ */ jsxs("div", { children: [
    /* @__PURE__ */ jsx("h2", { className: "text-2xl font-bold text-gray-900 mb-2", children: "Choose Your Platform" }),
    /* @__PURE__ */ jsx("p", { className: "text-gray-600 mb-6", children: "Select the operating system for which you want to generate an installation script." }),
    /* @__PURE__ */ jsx("div", { className: "grid md:grid-cols-3 gap-4 mb-8", children: platforms.map((platform) => /* @__PURE__ */ jsxs(
      "button",
      {
        onClick: () => handlePlatformSelect(platform.id),
        className: `
              p-6 rounded-lg border-2 transition-all duration-200 text-left
              ${formState.platform === platform.id ? "border-blue-500 bg-blue-50 ring-2 ring-blue-200" : platform.color}
            `,
        children: [
          /* @__PURE__ */ jsx("div", { className: "text-3xl mb-3", children: platform.icon }),
          /* @__PURE__ */ jsx("h3", { className: "text-lg font-semibold text-gray-900 mb-2", children: platform.name }),
          /* @__PURE__ */ jsx("p", { className: "text-sm text-gray-600", children: platform.description })
        ]
      },
      platform.id
    )) }),
    /* @__PURE__ */ jsx("div", { className: "flex justify-end", children: /* @__PURE__ */ jsx(
      "button",
      {
        onClick: onNext,
        disabled: !formState.platform,
        className: "px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors",
        children: "Next Step →"
      }
    ) })
  ] });
}

const generator$2 = new ScriptGenerator$1();
function DistributionStep({ formState, onUpdate, onNext, onPrevious }) {
  const distributions = generator$2.getDistributions();
  const handleDistributionSelect = (distribution) => {
    onUpdate({ distribution });
  };
  return /* @__PURE__ */ jsxs("div", { children: [
    /* @__PURE__ */ jsx("h2", { className: "text-2xl font-bold text-gray-900 mb-2", children: "Choose Linux Distribution" }),
    /* @__PURE__ */ jsx("p", { className: "text-gray-600 mb-6", children: "Select your Linux distribution to use the appropriate package manager." }),
    /* @__PURE__ */ jsx("div", { className: "grid md:grid-cols-2 gap-4 mb-8", children: Object.entries(distributions).map(([id, dist]) => /* @__PURE__ */ jsxs(
      "button",
      {
        onClick: () => handleDistributionSelect(id),
        className: `
              p-4 rounded-lg border-2 transition-all duration-200 text-left
              ${formState.distribution === id ? "border-blue-500 bg-blue-50 ring-2 ring-blue-200" : "bg-white border-gray-200 hover:bg-gray-50"}
            `,
        children: [
          /* @__PURE__ */ jsx("h3", { className: "text-lg font-semibold text-gray-900 mb-2", children: dist.name }),
          /* @__PURE__ */ jsxs("p", { className: "text-sm text-gray-600", children: [
            "Package Manager: ",
            /* @__PURE__ */ jsx("code", { className: "bg-gray-100 px-2 py-1 rounded text-xs", children: dist.packageManager })
          ] })
        ]
      },
      id
    )) }),
    /* @__PURE__ */ jsxs("div", { className: "flex justify-between", children: [
      /* @__PURE__ */ jsx(
        "button",
        {
          onClick: onPrevious,
          className: "px-6 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors",
          children: "← Previous"
        }
      ),
      /* @__PURE__ */ jsx(
        "button",
        {
          onClick: onNext,
          disabled: !formState.distribution,
          className: "px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors",
          children: "Next Step →"
        }
      )
    ] })
  ] });
}

const generator$1 = new ScriptGenerator$1();
function ApplicationStep({
  formState,
  onUpdate,
  onPrevious,
  onGenerate
}) {
  const [searchTerm, setSearchTerm] = useState("");
  const [activeCategory, setActiveCategory] = useState("all");
  const applications = generator$1.getApplications();
  const categories = generator$1.getCategories();
  const filteredApps = Object.entries(applications).filter(([id, app]) => {
    const matchesSearch = app.name.toLowerCase().includes(searchTerm.toLowerCase()) || app.description.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesCategory = activeCategory === "all" || app.category === activeCategory;
    const supportsPlatform = formState.platform in app.platforms;
    return matchesSearch && matchesCategory && supportsPlatform;
  });
  const handleAppToggle = (appId) => {
    const updatedApps = formState.selectedApps.includes(appId) ? formState.selectedApps.filter((id) => id !== appId) : [...formState.selectedApps, appId];
    onUpdate({ selectedApps: updatedApps });
  };
  const handleSelectAll = () => {
    const allAppIds = filteredApps.map(([id]) => id);
    const allSelected = allAppIds.every(
      (id) => formState.selectedApps.includes(id)
    );
    if (allSelected) {
      onUpdate({
        selectedApps: formState.selectedApps.filter(
          (id) => !allAppIds.includes(id)
        )
      });
    } else {
      const newSelection = [
        .../* @__PURE__ */ new Set([...formState.selectedApps, ...allAppIds])
      ];
      onUpdate({ selectedApps: newSelection });
    }
  };
  return /* @__PURE__ */ jsxs("div", { children: [
    /* @__PURE__ */ jsx("h2", { className: "text-2xl font-bold text-gray-900 mb-2", children: "Select Applications" }),
    /* @__PURE__ */ jsxs("p", { className: "text-gray-600 mb-6", children: [
      "Choose the applications you want to install on",
      " ",
      formState.platform === "linux" ? `${formState.distribution}` : formState.platform,
      "."
    ] }),
    /* @__PURE__ */ jsxs("div", { className: "mb-6 space-y-4", children: [
      /* @__PURE__ */ jsxs("div", { className: "relative", children: [
        /* @__PURE__ */ jsx(
          "input",
          {
            type: "text",
            placeholder: "Search applications...",
            value: searchTerm,
            onChange: (e) => setSearchTerm(e.target.value),
            className: "w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          }
        ),
        /* @__PURE__ */ jsx("div", { className: "absolute inset-y-0 right-0 flex items-center pr-3", children: /* @__PURE__ */ jsx("span", { className: "text-gray-400", children: "🔍" }) })
      ] }),
      /* @__PURE__ */ jsxs("div", { className: "flex flex-wrap gap-2", children: [
        /* @__PURE__ */ jsx(
          "button",
          {
            onClick: () => setActiveCategory("all"),
            className: `px-3 py-1 rounded-full text-sm transition-colors ${activeCategory === "all" ? "bg-blue-600 text-white" : "bg-gray-200 text-gray-700 hover:bg-gray-300"}`,
            children: "All Categories"
          }
        ),
        Object.entries(categories).map(([id, category]) => /* @__PURE__ */ jsxs(
          "button",
          {
            onClick: () => setActiveCategory(id),
            className: `px-3 py-1 rounded-full text-sm transition-colors ${activeCategory === id ? "bg-blue-600 text-white" : "bg-gray-200 text-gray-700 hover:bg-gray-300"}`,
            children: [
              category.icon,
              " ",
              category.name
            ]
          },
          id
        ))
      ] }),
      /* @__PURE__ */ jsxs("div", { className: "flex items-center justify-between", children: [
        /* @__PURE__ */ jsx(
          "button",
          {
            onClick: handleSelectAll,
            className: "text-blue-600 hover:text-blue-700 text-sm font-medium",
            children: filteredApps.every(([id]) => formState.selectedApps.includes(id)) ? "Deselect All" : "Select All"
          }
        ),
        /* @__PURE__ */ jsxs("span", { className: "text-sm text-gray-500", children: [
          formState.selectedApps.length,
          " applications selected"
        ] })
      ] })
    ] }),
    /* @__PURE__ */ jsx("div", { className: "grid md:grid-cols-2 lg:grid-cols-3 gap-4 mb-8 max-h-96 overflow-y-auto", children: filteredApps.map(([id, app]) => /* @__PURE__ */ jsxs(
      "label",
      {
        className: `
              flex items-start p-4 border-2 rounded-lg cursor-pointer transition-all duration-200
              ${formState.selectedApps.includes(id) ? "border-blue-500 bg-blue-50" : "border-gray-200 hover:border-gray-300"}
            `,
        children: [
          /* @__PURE__ */ jsx(
            "input",
            {
              type: "checkbox",
              checked: formState.selectedApps.includes(id),
              onChange: () => handleAppToggle(id),
              className: "mt-1 mr-3 h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
            }
          ),
          /* @__PURE__ */ jsxs("div", { className: "flex-1 min-w-0", children: [
            /* @__PURE__ */ jsx("h4", { className: "text-sm font-medium text-gray-900 mb-1", children: app.name }),
            /* @__PURE__ */ jsx("p", { className: "text-xs text-gray-600 line-clamp-2", children: app.description }),
            /* @__PURE__ */ jsxs("span", { className: "inline-block mt-2 px-2 py-1 text-xs bg-gray-100 text-gray-600 rounded", children: [
              categories[app.category]?.icon,
              " ",
              categories[app.category]?.name
            ] })
          ] })
        ]
      },
      id
    )) }),
    filteredApps.length === 0 && /* @__PURE__ */ jsxs("div", { className: "text-center py-8 text-gray-500", children: [
      /* @__PURE__ */ jsx("div", { className: "text-4xl mb-2", children: "📦" }),
      /* @__PURE__ */ jsx("p", { children: "No applications found matching your criteria." })
    ] }),
    /* @__PURE__ */ jsxs("div", { className: "flex justify-between", children: [
      /* @__PURE__ */ jsx(
        "button",
        {
          onClick: onPrevious,
          className: "px-6 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors",
          children: "← Previous"
        }
      ),
      /* @__PURE__ */ jsx(
        "button",
        {
          onClick: onGenerate,
          disabled: formState.selectedApps.length === 0,
          className: "px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors",
          children: "Generate Script 🚀"
        }
      )
    ] })
  ] });
}

function PreviewStep({ formState, onPrevious, onReset }) {
  const [copied, setCopied] = useState(false);
  const [quickCommand, setQuickCommand] = useState("");
  const [commandCopied, setCommandCopied] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState("");
  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(formState.generatedScript);
      setCopied(true);
      setTimeout(() => setCopied(false), 2e3);
    } catch (err) {
      console.error("Failed to copy text: ", err);
    }
  };
  const downloadScript = () => {
    const element = document.createElement("a");
    const file = new Blob([formState.generatedScript], { type: "text/plain" });
    element.href = URL.createObjectURL(file);
    const extension = formState.platform === "windows" ? "ps1" : "sh";
    const filename = `install-script.${extension}`;
    element.download = filename;
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
  };
  const generateQuickCommand = async () => {
    if (formState.platform === "windows") {
      setError("Quick install commands are only available for macOS and Linux");
      return;
    }
    setIsGenerating(true);
    setError("");
    try {
      const response = await fetch("/api/generate-script", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          platform: formState.platform,
          distribution: formState.distribution,
          selectedApps: formState.selectedApps
        })
      });
      if (!response.ok) {
        throw new Error("Failed to generate quick command");
      }
      const data = await response.json();
      setQuickCommand(data.command);
    } catch (err) {
      setError("Failed to generate quick install command. Please try again.");
      console.error("Error generating command:", err);
    } finally {
      setIsGenerating(false);
    }
  };
  const copyCommandToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(quickCommand);
      setCommandCopied(true);
      setTimeout(() => setCommandCopied(false), 2e3);
    } catch (err) {
      console.error("Failed to copy command: ", err);
    }
  };
  const getFileExtension = () => {
    return formState.platform === "windows" ? "ps1" : "sh";
  };
  const getLanguage = () => {
    return formState.platform === "windows" ? "powershell" : "bash";
  };
  return /* @__PURE__ */ jsxs("div", { children: [
    /* @__PURE__ */ jsx("h2", { className: "text-2xl font-bold text-gray-900 mb-2", children: "Your Installation Script" }),
    /* @__PURE__ */ jsxs("p", { className: "text-gray-600 mb-6", children: [
      "Your custom installation script is ready! Copy it or download as a .",
      getFileExtension(),
      " file."
    ] }),
    /* @__PURE__ */ jsx("div", { className: "bg-gray-50 rounded-lg p-4 mb-4", children: /* @__PURE__ */ jsxs("div", { className: "grid grid-cols-1 md:grid-cols-3 gap-4 text-sm", children: [
      /* @__PURE__ */ jsxs("div", { children: [
        /* @__PURE__ */ jsx("span", { className: "font-medium text-gray-700", children: "Platform:" }),
        /* @__PURE__ */ jsxs("div", { className: "mt-1", children: [
          formState.platform === "windows" && "🪟 Windows",
          formState.platform === "macos" && "🍎 macOS",
          formState.platform === "linux" && `🐧 Linux (${formState.distribution})`
        ] })
      ] }),
      /* @__PURE__ */ jsxs("div", { children: [
        /* @__PURE__ */ jsx("span", { className: "font-medium text-gray-700", children: "Applications:" }),
        /* @__PURE__ */ jsxs("div", { className: "mt-1", children: [
          formState.selectedApps.length,
          " selected"
        ] })
      ] }),
      /* @__PURE__ */ jsxs("div", { children: [
        /* @__PURE__ */ jsx("span", { className: "font-medium text-gray-700", children: "File Type:" }),
        /* @__PURE__ */ jsxs("div", { className: "mt-1", children: [
          ".",
          getFileExtension(),
          " (",
          getLanguage(),
          ")"
        ] })
      ] })
    ] }) }),
    /* @__PURE__ */ jsxs("div", { className: "relative", children: [
      /* @__PURE__ */ jsxs("div", { className: "absolute top-4 right-4 flex space-x-2 z-10", children: [
        /* @__PURE__ */ jsx(
          "button",
          {
            onClick: copyToClipboard,
            className: `px-3 py-1 rounded text-sm font-medium transition-colors ${copied ? "bg-green-600 text-white" : "bg-gray-600 text-white hover:bg-gray-700"}`,
            children: copied ? "✓ Copied!" : "📋 Copy"
          }
        ),
        /* @__PURE__ */ jsx(
          "button",
          {
            onClick: downloadScript,
            className: "px-3 py-1 bg-blue-600 text-white rounded text-sm font-medium hover:bg-blue-700 transition-colors",
            children: "💾 Download"
          }
        )
      ] }),
      /* @__PURE__ */ jsx("pre", { className: "bg-gray-900 text-gray-100 p-6 rounded-lg overflow-x-auto text-sm", children: /* @__PURE__ */ jsx("code", { children: formState.generatedScript }) })
    ] }),
    (formState.platform === "macos" || formState.platform === "linux") && /* @__PURE__ */ jsxs("div", { className: "mt-6 bg-gradient-to-r from-purple-50 to-blue-50 border border-purple-200 rounded-lg p-6", children: [
      /* @__PURE__ */ jsxs("h3", { className: "font-bold text-purple-900 mb-3 flex items-center", children: [
        "⚡ Quick Install Command",
        /* @__PURE__ */ jsx("span", { className: "ml-2 text-xs bg-purple-200 text-purple-800 px-2 py-1 rounded", children: "NEW" })
      ] }),
      /* @__PURE__ */ jsx("p", { className: "text-purple-800 text-sm mb-4", children: "Generate a one-line command that others can copy and run directly in their terminal. Perfect for sharing with teammates or documentation!" }),
      !quickCommand && /* @__PURE__ */ jsx(
        "button",
        {
          onClick: generateQuickCommand,
          disabled: isGenerating,
          className: "px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors disabled:opacity-50 flex items-center",
          children: isGenerating ? /* @__PURE__ */ jsxs(Fragment, { children: [
            /* @__PURE__ */ jsxs("svg", { className: "animate-spin -ml-1 mr-3 h-4 w-4 text-white", xmlns: "http://www.w3.org/2000/svg", fill: "none", viewBox: "0 0 24 24", children: [
              /* @__PURE__ */ jsx("circle", { className: "opacity-25", cx: "12", cy: "12", r: "10", stroke: "currentColor", strokeWidth: "4" }),
              /* @__PURE__ */ jsx("path", { className: "opacity-75", fill: "currentColor", d: "M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" })
            ] }),
            "Generating..."
          ] }) : "🚀 Generate Quick Command"
        }
      ),
      error && /* @__PURE__ */ jsx("div", { className: "mt-4 p-3 bg-red-100 border border-red-300 rounded text-red-700 text-sm", children: error }),
      quickCommand && /* @__PURE__ */ jsxs("div", { className: "mt-4", children: [
        /* @__PURE__ */ jsxs("div", { className: "flex items-center justify-between mb-2", children: [
          /* @__PURE__ */ jsx("span", { className: "font-medium text-purple-900", children: "Your Quick Install Command:" }),
          /* @__PURE__ */ jsx(
            "button",
            {
              onClick: copyCommandToClipboard,
              className: `px-3 py-1 rounded text-xs font-medium transition-colors ${commandCopied ? "bg-green-500 text-white" : "bg-purple-600 text-white hover:bg-purple-700"}`,
              children: commandCopied ? "✓ Copied!" : "📋 Copy"
            }
          )
        ] }),
        /* @__PURE__ */ jsx("div", { className: "bg-gray-900 text-green-400 p-3 rounded font-mono text-sm overflow-x-auto", children: quickCommand }),
        /* @__PURE__ */ jsx("p", { className: "text-xs text-purple-700 mt-2", children: "⏰ This command expires in 10 minutes for security" })
      ] })
    ] }),
    /* @__PURE__ */ jsxs("div", { className: "mt-6 bg-blue-50 border border-blue-200 rounded-lg p-4", children: [
      /* @__PURE__ */ jsx("h3", { className: "font-medium text-blue-900 mb-2", children: "📋 Usage Instructions" }),
      /* @__PURE__ */ jsxs("div", { className: "text-sm text-blue-800 space-y-2", children: [
        formState.platform === "windows" && /* @__PURE__ */ jsxs(Fragment, { children: [
          /* @__PURE__ */ jsxs("p", { children: [
            "1. Save the script as ",
            /* @__PURE__ */ jsx("code", { children: "install-script.ps1" })
          ] }),
          /* @__PURE__ */ jsx("p", { children: '2. Right-click on the file and select "Run with PowerShell"' }),
          /* @__PURE__ */ jsxs("p", { children: [
            "3. Or run from PowerShell as Administrator: ",
            /* @__PURE__ */ jsx("code", { children: ".\\install-script.ps1" })
          ] })
        ] }),
        (formState.platform === "macos" || formState.platform === "linux") && /* @__PURE__ */ jsxs(Fragment, { children: [
          /* @__PURE__ */ jsx("p", { children: /* @__PURE__ */ jsx("strong", { children: "Option 1 - Quick Command:" }) }),
          /* @__PURE__ */ jsx("p", { children: "• Generate a quick command above and share it with others" }),
          /* @__PURE__ */ jsx("p", { children: "• Recipients can copy-paste directly into terminal" }),
          /* @__PURE__ */ jsx("p", { className: "mb-3", children: "• No file download needed!" }),
          /* @__PURE__ */ jsx("p", { children: /* @__PURE__ */ jsx("strong", { children: "Option 2 - Manual Download:" }) }),
          /* @__PURE__ */ jsxs("p", { children: [
            "1. Save the script as ",
            /* @__PURE__ */ jsx("code", { children: "install-script.sh" })
          ] }),
          /* @__PURE__ */ jsxs("p", { children: [
            "2. Make it executable: ",
            /* @__PURE__ */ jsx("code", { children: "chmod +x install-script.sh" })
          ] }),
          /* @__PURE__ */ jsxs("p", { children: [
            "3. Run the script: ",
            /* @__PURE__ */ jsx("code", { children: "./install-script.sh" })
          ] })
        ] })
      ] })
    ] }),
    /* @__PURE__ */ jsxs("div", { className: "flex justify-between mt-8", children: [
      /* @__PURE__ */ jsx(
        "button",
        {
          onClick: onPrevious,
          className: "px-6 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors",
          children: "← Edit Selection"
        }
      ),
      /* @__PURE__ */ jsx(
        "button",
        {
          onClick: onReset,
          className: "px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors",
          children: "🎉 Create Another Script"
        }
      )
    ] })
  ] });
}

function ProgressBar({ currentStep, platform }) {
  const steps = [
    { number: 1, title: "Platform", icon: "💻" },
    { number: 2, title: "Distribution", icon: "🐧", onlyLinux: true },
    { number: 3, title: "Applications", icon: "📦" },
    { number: 4, title: "Preview", icon: "👀" }
  ];
  const visibleSteps = steps.filter(
    (step) => !step.onlyLinux || platform === "linux"
  );
  return /* @__PURE__ */ jsx("div", { className: "flex items-center justify-center", children: visibleSteps.map((step, index) => /* @__PURE__ */ jsxs(React.Fragment, { children: [
    /* @__PURE__ */ jsxs("div", { className: "flex items-center", children: [
      /* @__PURE__ */ jsx("div", { className: `
              flex items-center justify-center w-12 h-12 rounded-full border-2
              ${currentStep >= step.number ? "bg-blue-600 border-blue-600 text-white" : "bg-white border-gray-300 text-gray-500"}
            `, children: /* @__PURE__ */ jsx("span", { className: "text-sm font-semibold", children: currentStep > step.number ? "✓" : step.icon }) }),
      /* @__PURE__ */ jsxs("div", { className: "ml-3 text-sm", children: [
        /* @__PURE__ */ jsxs("p", { className: `font-medium ${currentStep >= step.number ? "text-blue-600" : "text-gray-500"}`, children: [
          "Step ",
          index + 1
        ] }),
        /* @__PURE__ */ jsx("p", { className: "text-gray-500", children: step.title })
      ] })
    ] }),
    index < visibleSteps.length - 1 && /* @__PURE__ */ jsx("div", { className: `
              flex-1 h-0.5 mx-8
              ${currentStep > step.number ? "bg-blue-600" : "bg-gray-300"}
            ` })
  ] }, step.number)) });
}

const generator = new ScriptGenerator$1();
function ScriptGenerator() {
  const [formState, setFormState] = useState({
    step: 1,
    platform: "",
    distribution: "",
    selectedApps: [],
    generatedScript: ""
  });
  const updateFormState = (updates) => {
    setFormState((prev) => ({ ...prev, ...updates }));
  };
  const nextStep = () => {
    if (formState.step < 4) {
      let nextStepNum = formState.step + 1;
      if (nextStepNum === 2 && formState.platform !== "linux") {
        nextStepNum = 3;
      }
      setFormState((prev) => ({ ...prev, step: nextStepNum }));
    }
  };
  const previousStep = () => {
    if (formState.step > 1) {
      let prevStepNum = formState.step - 1;
      if (prevStepNum === 2 && formState.platform !== "linux") {
        prevStepNum = 1;
      }
      setFormState((prev) => ({ ...prev, step: prevStepNum }));
    }
  };
  const generateScript = () => {
    try {
      const script = generator.generateScript({
        platform: formState.platform,
        distribution: formState.distribution,
        selectedApps: formState.selectedApps
      });
      updateFormState({ generatedScript: script, step: 4 });
    } catch (error) {
      console.error("Error generating script:", error);
    }
  };
  const resetForm = () => {
    setFormState({
      step: 1,
      platform: "",
      distribution: "",
      selectedApps: [],
      generatedScript: ""
    });
  };
  const stepProps = {
    formState,
    onUpdate: updateFormState,
    onNext: nextStep,
    onPrevious: previousStep
  };
  return /* @__PURE__ */ jsxs("div", { className: "max-w-4xl mx-auto p-6", children: [
    /* @__PURE__ */ jsxs("div", { className: "text-center mb-8", children: [
      /* @__PURE__ */ jsx("h1", { className: "text-4xl font-bold text-gray-900 mb-2", children: "Script Installer Generator" }),
      /* @__PURE__ */ jsx("p", { className: "text-xl text-gray-600", children: "Generate custom installation scripts for Windows, macOS, and Linux" })
    ] }),
    /* @__PURE__ */ jsx(
      ProgressBar,
      {
        currentStep: formState.step,
        platform: formState.platform
      }
    ),
    /* @__PURE__ */ jsxs("div", { className: "bg-white rounded-lg shadow-lg p-8 mt-8", children: [
      formState.step === 1 && /* @__PURE__ */ jsx(PlatformStep, { ...stepProps }),
      formState.step === 2 && /* @__PURE__ */ jsx(DistributionStep, { ...stepProps }),
      formState.step === 3 && /* @__PURE__ */ jsx(
        ApplicationStep,
        {
          ...stepProps,
          onGenerate: generateScript
        }
      ),
      formState.step === 4 && /* @__PURE__ */ jsx(
        PreviewStep,
        {
          ...stepProps,
          onReset: resetForm
        }
      )
    ] })
  ] });
}

const $$Astro = createAstro("https://script-installer-generator.vercel.app");
const $$Index = createComponent(($$result, $$props, $$slots) => {
  const Astro2 = $$result.createAstro($$Astro, $$props, $$slots);
  Astro2.self = $$Index;
  return renderTemplate`<html lang="en"> <head><meta charset="utf-8"><link rel="icon" type="image/svg+xml" href="/favicon.svg"><meta name="viewport" content="width=device-width"><meta name="generator"${addAttribute(Astro2.generator, "content")}><title>Script Installer Generator</title><meta name="description" content="Generate custom installation scripts for Windows, macOS, and Linux with popular applications.">${renderHead()}</head> <body class="bg-gray-50 min-h-screen"> <main class="container mx-auto py-8"> ${renderComponent($$result, "ScriptGenerator", ScriptGenerator, { "client:load": true, "client:component-hydration": "load", "client:component-path": "/Users/laruina/Documents/GIT/scripts/my-script-generator/src/components/ScriptGenerator", "client:component-export": "ScriptGenerator" })} </main> </body></html>`;
}, "/Users/laruina/Documents/GIT/scripts/my-script-generator/src/pages/index.astro", void 0);

const $$file = "/Users/laruina/Documents/GIT/scripts/my-script-generator/src/pages/index.astro";
const $$url = "";

const _page = /*#__PURE__*/Object.freeze(/*#__PURE__*/Object.defineProperty({
  __proto__: null,
  default: $$Index,
  file: $$file,
  url: $$url
}, Symbol.toStringTag, { value: 'Module' }));

const page = () => _page;

export { page };
