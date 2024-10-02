import openai

# Replace with your OpenAI API key
openai.api_key = '***OPENAI API KEY***'

def get_university_recommendations(profile_summary):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an assistant that provides university recommendations based on user profiles."},
                {"role": "user", "content": f"Based on the following profile, suggest the best universities: {profile_summary}"}
            ]
        )

        recommendations = response['choices'][0]['message']['content'].strip()
        return recommendations

    except openai.error.OpenAIError as e:
        print(f"An error occurred: {e}")
        return "An error occurred while fetching recommendations."

