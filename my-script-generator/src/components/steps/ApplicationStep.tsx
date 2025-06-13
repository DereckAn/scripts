import React, { useState } from "react";
import type { StepProps } from "../../lib/types";
import { ScriptGenerator } from "../../lib/scriptGenerator";

const generator = new ScriptGenerator();

interface ApplicationStepProps extends StepProps {
  onGenerate: () => void;
}

export function ApplicationStep({
  formState,
  onUpdate,
  onPrevious,
  onGenerate,
}: ApplicationStepProps) {
  const [searchTerm, setSearchTerm] = useState("");
  const [activeCategory, setActiveCategory] = useState<string>("all");

  const applications = generator.getApplications();
  const categories = generator.getCategories();

  const filteredApps = Object.entries(applications).filter(([id, app]) => {
    const matchesSearch =
      app.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      app.description.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesCategory =
      activeCategory === "all" || app.category === activeCategory;
    const supportsPlatform = formState.platform in app.platforms;

    return matchesSearch && matchesCategory && supportsPlatform;
  });

  const handleAppToggle = (appId: string) => {
    const updatedApps = formState.selectedApps.includes(appId)
      ? formState.selectedApps.filter((id) => id !== appId)
      : [...formState.selectedApps, appId];

    onUpdate({ selectedApps: updatedApps });
  };

  const handleSelectAll = () => {
    const allAppIds = filteredApps.map(([id]) => id);
    const allSelected = allAppIds.every((id) =>
      formState.selectedApps.includes(id),
    );

    if (allSelected) {
      onUpdate({
        selectedApps: formState.selectedApps.filter(
          (id) => !allAppIds.includes(id),
        ),
      });
    } else {
      const newSelection = [
        ...new Set([...formState.selectedApps, ...allAppIds]),
      ];
      onUpdate({ selectedApps: newSelection });
    }
  };

  return (
    <div>
      <h2 className="text-2xl font-bold text-gray-900 mb-2">
        Select Applications
      </h2>
      <p className="text-gray-600 mb-6">
        Choose the applications you want to install on{" "}
        {formState.platform === "linux"
          ? `${formState.distribution}`
          : formState.platform}
        .
      </p>

      {/* Search and Filters */}
      <div className="mb-6 space-y-4">
        <div className="relative">
          <input
            type="text"
            placeholder="Search applications..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
          <div className="absolute inset-y-0 right-0 flex items-center pr-3">
            <span className="text-gray-400">🔍</span>
          </div>
        </div>

        {/* Category Filter */}
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => setActiveCategory("all")}
            className={`px-3 py-1 rounded-full text-sm transition-colors ${
              activeCategory === "all"
                ? "bg-blue-600 text-white"
                : "bg-gray-200 text-gray-700 hover:bg-gray-300"
            }`}
          >
            All Categories
          </button>
          {Object.entries(categories).map(([id, category]) => (
            <button
              key={id}
              onClick={() => setActiveCategory(id)}
              className={`px-3 py-1 rounded-full text-sm transition-colors ${
                activeCategory === id
                  ? "bg-blue-600 text-white"
                  : "bg-gray-200 text-gray-700 hover:bg-gray-300"
              }`}
            >
              {category.icon} {category.name}
            </button>
          ))}
        </div>

        {/* Select All */}
        <div className="flex items-center justify-between">
          <button
            onClick={handleSelectAll}
            className="text-blue-600 hover:text-blue-700 text-sm font-medium"
          >
            {filteredApps.every(([id]) => formState.selectedApps.includes(id))
              ? "Deselect All"
              : "Select All"}
          </button>
          <span className="text-sm text-gray-500">
            {formState.selectedApps.length} applications selected
          </span>
        </div>
      </div>

      {/* Applications Grid */}
      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4 mb-8 max-h-96 overflow-y-auto">
        {filteredApps.map(([id, app]) => (
          <label
            key={id}
            className={`
              flex items-start p-4 border-2 rounded-lg cursor-pointer transition-all duration-200
              ${
                formState.selectedApps.includes(id)
                  ? "border-blue-500 bg-blue-50"
                  : "border-gray-200 hover:border-gray-300"
              }
            `}
          >
            <input
              type="checkbox"
              checked={formState.selectedApps.includes(id)}
              onChange={() => handleAppToggle(id)}
              className="mt-1 mr-3 h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
            />
            <div className="flex-1 min-w-0">
              <h4 className="text-sm font-medium text-gray-900 mb-1">
                {app.name}
              </h4>
              <p className="text-xs text-gray-600 line-clamp-2">
                {app.description}
              </p>
              <span className="inline-block mt-2 px-2 py-1 text-xs bg-gray-100 text-gray-600 rounded">
                {categories[app.category]?.icon}{" "}
                {categories[app.category]?.name}
              </span>
            </div>
          </label>
        ))}
      </div>

      {filteredApps.length === 0 && (
        <div className="text-center py-8 text-gray-500">
          <div className="text-4xl mb-2">📦</div>
          <p>No applications found matching your criteria.</p>
        </div>
      )}

      <div className="flex justify-between">
        <button
          onClick={onPrevious}
          className="px-6 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors"
        >
          ← Previous
        </button>
        <button
          onClick={onGenerate}
          disabled={formState.selectedApps.length === 0}
          className="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
        >
          Generate Script 🚀
        </button>
      </div>
    </div>
  );
}
